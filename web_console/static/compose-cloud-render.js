(() => {
  const previewButton = document.querySelector('#preview');
  const finalButton = document.querySelector('#final');
  const applyButton = document.querySelector('#apply');
  const statusBox = document.querySelector('#status');
  if (!previewButton || !finalButton || !applyButton || !statusBox) return;

  let busy = false;
  let pollTimer = 0;

  const apiUrlFor = path => {
    if (typeof apiUrl === 'function') return apiUrl(path);
    return new URL(String(path).replace(/^\/+/, ''), new URL('./', location.href)).toString();
  };

  const projectValue = () => {
    if (typeof projectName === 'function') return projectName();
    return document.querySelector('#project')?.value?.trim() || '';
  };

  const setLocalStatus = message => {
    if (typeof setStatus === 'function') setStatus(message);
    else statusBox.textContent = message;
  };

  async function request(path, options = {}) {
    if (typeof requestJson === 'function') return requestJson(path, options);
    const response = await fetch(apiUrlFor(path), options);
    const text = await response.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; }
    catch { data = {detail: text || `HTTP ${response.status}`}; }
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    return data;
  }

  function setBusy(value) {
    busy = value;
    previewButton.disabled = value;
    finalButton.disabled = value;
    applyButton.disabled = value;
  }

  function form(fields) {
    const body = new FormData();
    Object.entries(fields).forEach(([key, value]) => body.append(key, String(value)));
    return body;
  }

  function stopPolling() {
    if (pollTimer) window.clearTimeout(pollTimer);
    pollTimer = 0;
  }

  async function pollStatus(requestId, label, startedAt = Date.now()) {
    stopPolling();
    try {
      const record = await request(`api/cloud-render/status/${encodeURIComponent(requestId)}`, {cache: 'no-store'});
      const execution = record.execution ? `\n実行ID: ${record.execution}` : '';
      if (record.status === 'COMPLETED') {
        setLocalStatus(`${label}のクラウド書き出しが完了しました。\n出力: ${record.output_uri || ''}`);
        setBusy(false);
        if (typeof load === 'function') await load();
        return;
      }
      if (record.status === 'FAILED' || record.status === 'REJECTED') {
        throw new Error(record.error || `クラウド書き出しが${record.status}になりました`);
      }
      if (Date.now() - startedAt > 10 * 60 * 1000) {
        setLocalStatus(`${label}はCloud Runで処理中です。画面を閉じても実行は継続します。${execution}\n後でこの画面を開き直して状態を確認してください。`);
        setBusy(false);
        return;
      }
      setLocalStatus(`${label}をCloud Runで処理中です。状態: ${record.status}${execution}`);
      pollTimer = window.setTimeout(() => pollStatus(requestId, label, startedAt), 5000);
    } catch (error) {
      setBusy(false);
      setLocalStatus(`${label}状態確認失敗:\n${error?.message || error}`);
    }
  }

  async function cloudRender(mode) {
    if (busy) return;
    const project = projectValue();
    const label = mode === 'preview' ? 'プレビュー' : '最終版';
    if (!project) {
      setLocalStatus('プロジェクト名を入力してください。');
      return;
    }

    setBusy(true);
    setLocalStatus(`${label}の素材を安全確認し、クラウド投入準備をしています…`);
    try {
      const prepared = await request('api/cloud-render/prepare-project', {
        method: 'POST',
        body: form({project, mode}),
      });
      const confirmation = String(prepared.confirmation || '');
      const maxYen = Number(prepared.estimated_max_yen || 0);
      const files = Number(prepared.security?.files || 0);
      const approved = window.confirm(
        `${label}を書き出します。\n\n` +
        `安全確認済み素材: ${files}件\n` +
        `費用上限: ${maxYen}円\n` +
        `承認はこの1回だけ有効です。自動公開は行いません。\n\n` +
        `「OK」で ${confirmation} を承認します。`
      );
      if (!approved) {
        setLocalStatus(`${label}の実行を取り消しました。Cloud Runは起動していません。`);
        setBusy(false);
        return;
      }

      setLocalStatus(`${label}の一回承認を確定しています…`);
      await request('api/cloud-render/approve', {
        method: 'POST',
        body: form({request_id: prepared.request_id, confirmation}),
      });

      setLocalStatus(`${label}をCloud Runへ投入しています…`);
      const dispatched = await request('api/cloud-render/dispatch', {
        method: 'POST',
        body: form({request_id: prepared.request_id}),
      });
      setLocalStatus(`${label}をCloud Runへ投入しました。\n実行ID: ${dispatched.execution || '確認中'}`);
      await pollStatus(prepared.request_id, label);
    } catch (error) {
      setBusy(false);
      setLocalStatus(`${label}書き出し準備失敗:\n${error?.message || error}`);
    }
  }

  function bind(button, mode) {
    const handler = event => {
      event.preventDefault();
      event.stopImmediatePropagation();
      cloudRender(mode);
    };
    button.addEventListener('click', handler, true);
  }

  bind(previewButton, 'preview');
  bind(finalButton, 'final');

  window.addEventListener('pagehide', stopPolling);
})();
