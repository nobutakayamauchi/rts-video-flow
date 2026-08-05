(() => {
  const statusBox = document.querySelector('#status');
  if (!statusBox) return;

  let busy = false;
  let pollTimer = 0;
  let lastActivationAt = 0;
  let lastActivationId = '';

  const progress = () => window.RTSProgressOverlay || null;

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

  function buttons() {
    return [document.querySelector('#preview'), document.querySelector('#final'), document.querySelector('#apply')].filter(Boolean);
  }

  function setBusy(value) {
    busy = value;
    buttons().forEach(button => {
      button.disabled = value;
      button.setAttribute('aria-busy', value ? 'true' : 'false');
    });
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
        const message = `${label}のクラウド書き出しが完了しました。\n出力: ${record.output_uri || ''}`;
        setLocalStatus(message);
        progress()?.finish({title: '✓ 書き出し完了', stage: `${label}が完成しました。`, note: record.output_uri || ''});
        setBusy(false);
        if (typeof load === 'function') await load();
        return;
      }
      if (record.status === 'FAILED' || record.status === 'REJECTED') {
        throw new Error(record.error || `クラウド書き出しが${record.status}になりました`);
      }
      if (Date.now() - startedAt > 10 * 60 * 1000) {
        const message = `${label}はCloud Runで処理中です。画面を閉じても実行は継続します。${execution}\n後でこの画面を開き直して状態を確認してください。`;
        setLocalStatus(message);
        progress()?.update({
          state: 'waiting',
          title: `${label}を処理中`,
          stage: `Cloud Run: ${record.status}`,
          note: '画面を閉じても処理は継続します。',
        });
        setBusy(false);
        return;
      }
      setLocalStatus(`${label}をCloud Runで処理中です。状態: ${record.status}${execution}`);
      progress()?.update({
        title: `${label}を処理中`,
        stage: `Cloud Run: ${record.status}`,
        note: record.execution ? `実行ID: ${record.execution}・画面を閉じても継続します。` : '画面を閉じても処理は継続します。',
      });
      pollTimer = window.setTimeout(() => pollStatus(requestId, label, startedAt), 5000);
    } catch (error) {
      setBusy(false);
      const detail = error?.message || error;
      setLocalStatus(`${label}状態確認失敗:\n${detail}`);
      progress()?.fail(detail, {title: `${label}の状態確認に失敗`});
    }
  }

  async function cloudRender(mode) {
    if (busy) {
      progress()?.update({title: 'すでに処理中です', note: '同じ操作を重複して開始しません。'});
      return;
    }
    const project = projectValue();
    const label = mode === 'preview' ? 'プレビュー' : '最終版';
    if (!project) {
      setLocalStatus('プロジェクト名を入力してください。');
      progress()?.fail('プロジェクト名を入力してください。', {title: '開始できません'});
      return;
    }

    setBusy(true);
    const acceptedMessage = `${label}のタップを受け付けました。素材を安全確認し、クラウド投入準備をしています…`;
    setLocalStatus(acceptedMessage);
    progress()?.show({
      title: '✓ 受け付けました',
      stage: `${label}用の素材を正規化・安全確認しています…`,
      note: '通常は約1分かかります。同じボタンを押し直す必要はありません。',
    });
    try {
      const prepared = await request('api/cloud-render/prepare-project', {
        method: 'POST',
        body: form({project, mode}),
      });
      progress()?.update({
        title: '✓ 書き出し準備完了',
        stage: `安全確認済み素材 ${Number(prepared.security?.files || 0)}件`,
        percent: 100,
        note: '実行承認を確認します。',
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
        progress()?.finish({title: '実行を取り消しました', stage: 'Cloud Runは起動していません。'});
        setBusy(false);
        return;
      }

      setLocalStatus(`${label}の一回承認を確定しています…`);
      progress()?.update({title: '承認を確定中', stage: 'この1回だけ有効な承認を記録しています…', percent: undefined});
      await request('api/cloud-render/approve', {
        method: 'POST',
        body: form({request_id: prepared.request_id, confirmation}),
      });

      setLocalStatus(`${label}をCloud Runへ投入しています…`);
      progress()?.update({title: `${label}を投入中`, stage: 'Cloud Runへジョブを送信しています…', note: '投入後は画面を閉じても処理が継続します。'});
      const dispatched = await request('api/cloud-render/dispatch', {
        method: 'POST',
        body: form({request_id: prepared.request_id}),
      });
      setLocalStatus(`${label}をCloud Runへ投入しました。\n実行ID: ${dispatched.execution || '確認中'}`);
      progress()?.update({title: `${label}を処理中`, stage: 'Cloud Runへ投入しました。', note: `実行ID: ${dispatched.execution || '確認中'}・画面を閉じても継続します。`});
      await pollStatus(prepared.request_id, label);
    } catch (error) {
      setBusy(false);
      const detail = error?.message || error;
      setLocalStatus(`${label}書き出し準備失敗:\n${detail}`);
      progress()?.fail(detail, {title: `${label}書き出し準備に失敗`});
    }
  }

  function delegatedActivation(event) {
    const target = event.target instanceof Element ? event.target.closest('#preview, #final') : null;
    if (!target) return;
    const now = Date.now();
    if (lastActivationId === target.id && now - lastActivationAt < 900) {
      event.preventDefault();
      event.stopImmediatePropagation();
      progress()?.update({title: busy ? 'すでに処理中です' : 'タップを受け付けました', note: busy ? '同じ処理を重複して開始しません。' : ''});
      return;
    }
    lastActivationId = target.id;
    lastActivationAt = now;
    event.preventDefault();
    event.stopImmediatePropagation();
    cloudRender(target.id === 'preview' ? 'preview' : 'final');
  }

  document.addEventListener('pointerup', delegatedActivation, true);
  document.addEventListener('touchend', delegatedActivation, {capture: true, passive: false});
  document.addEventListener('click', delegatedActivation, true);
  window.__rtsCloudRenderReady = true;
  window.addEventListener('pagehide', stopPolling);
})();
