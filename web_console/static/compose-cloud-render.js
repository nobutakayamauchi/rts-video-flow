(() => {
  const statusBox = document.querySelector('#status');
  if (!statusBox) return;

  let busy = false;
  let pollTimer = 0;
  let lastActivationAt = 0;
  let lastActivationId = '';
  let activeRequestId = '';
  let activeLabel = '';
  let activeStartedAt = 0;
  let reconnectAttempts = 0;
  let activeStep = 1;
  const TOTAL_STEPS = 7;

  const progress = () => window.RTSProgressOverlay || null;
  const stepPayload = (step, stage, extra = {}) => {
    activeStep = step;
    return {step, totalSteps: TOTAL_STEPS, stage, ...extra};
  };

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

  function renderButtons() {
    return [document.querySelector('#preview'), document.querySelector('#final')].filter(Boolean);
  }

  function setBusy(value) {
    busy = value;
    renderButtons().forEach(button => {
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

  function isConnectionError(error) {
    const detail = String(error?.message || error || '').toLowerCase();
    return detail.includes('load failed') || detail.includes('failed to fetch') || detail.includes('networkerror') || detail.includes('通信失敗') || detail.includes('network request failed');
  }

  function reconnectDelay(attempt) {
    if (attempt <= 3) return 5000;
    if (attempt <= 6) return 10000;
    return 15000;
  }

  function scheduleReconnect(requestId, label, startedAt, detail) {
    reconnectAttempts += 1;
    const delay = reconnectDelay(reconnectAttempts);
    const seconds = Math.round(delay / 1000);
    setLocalStatus(`${label}は処理を継続中です。通信が切れたため状態確認を再接続します。`);
    progress()?.update(stepPayload(activeStep, `${seconds}秒後に状態を再確認します`, {
      state: 'reconnecting',
      title: '再接続中',
      note: '画面操作やタブ移動は可能です。書き出し処理は継続しています。',
      onAction: () => pollStatus(requestId, label, startedAt, true),
      actionLabel: '今すぐ再接続',
    }));
    stopPolling();
    pollTimer = window.setTimeout(() => pollStatus(requestId, label, startedAt), delay);
    console.warn('cloud render status reconnect scheduled', {requestId, reconnectAttempts, detail});
  }

  async function pollStatus(requestId, label, startedAt = Date.now(), manual = false) {
    stopPolling();
    activeRequestId = requestId;
    activeLabel = label;
    activeStartedAt = startedAt;
    if (manual) {
      progress()?.update(stepPayload(activeStep, '状態を確認しています…', {
        state: 'reconnecting', title: '再接続中', note: '画面操作はそのまま続けられます。', onAction: null,
      }));
    }
    try {
      const record = await request(`api/cloud-render/status/${encodeURIComponent(requestId)}`, {cache: 'no-store'});
      reconnectAttempts = 0;
      const execution = record.execution ? `\n実行ID: ${record.execution}` : '';
      if (record.status === 'COMPLETED') {
        progress()?.update(stepPayload(6, '出力を確認しています…', {title: `${label}を処理中`, state: 'running', note: record.output_uri || ''}));
        const message = `${label}のクラウド書き出しが完了しました。\n出力: ${record.output_uri || ''}`;
        setLocalStatus(message);
        progress()?.finish({title: '✓ 書き出し完了', stage: `${label}が完成しました。`, note: record.output_uri || '', step: 7, totalSteps: TOTAL_STEPS});
        setBusy(false);
        activeRequestId = '';
        if (typeof load === 'function') await load();
        return;
      }
      if (record.status === 'FAILED' || record.status === 'REJECTED') throw new Error(record.error || `クラウド書き出しが${record.status}になりました`);

      activeStep = 5;
      if (Date.now() - startedAt > 10 * 60 * 1000) {
        setLocalStatus(`${label}はCloud Runで処理中です。画面を閉じても実行は継続します。${execution}`);
        progress()?.update(stepPayload(5, `動画を書き出しています（${record.status}）`, {
          state: 'waiting', title: `${label}を処理中`, note: '状態確認は継続します。画面操作やタブ移動も可能です。', onAction: null,
        }));
      } else {
        setLocalStatus(`${label}をCloud Runで処理中です。状態: ${record.status}${execution}`);
        progress()?.update(stepPayload(5, `動画を書き出しています（${record.status}）`, {
          state: 'running', title: `${label}を処理中`, note: record.execution ? `実行ID: ${record.execution}・画面操作は可能です。` : '画面操作は可能です。', onAction: null,
        }));
      }
      pollTimer = window.setTimeout(() => pollStatus(requestId, label, startedAt), 5000);
    } catch (error) {
      const detail = error?.message || error;
      if (isConnectionError(error)) {
        scheduleReconnect(requestId, label, startedAt, detail);
        return;
      }
      setBusy(false);
      activeRequestId = '';
      setLocalStatus(`${label}状態確認失敗:\n${detail}`);
      progress()?.fail(detail, {title: `${label}の状態確認に失敗`, step: activeStep, totalSteps: TOTAL_STEPS});
    }
  }

  async function cloudRender(mode) {
    if (busy) {
      progress()?.update({title: 'すでに処理中です', note: '同じ処理を重複して開始しません。画面操作は可能です。'});
      return;
    }
    const project = projectValue();
    const label = mode === 'preview' ? 'プレビュー' : '最終版';
    if (!project) {
      setLocalStatus('プロジェクト名を入力してください。');
      progress()?.fail('プロジェクト名を入力してください。', {title: '開始できません', step: 0, totalSteps: TOTAL_STEPS});
      return;
    }

    setBusy(true);
    activeStep = 1;
    setLocalStatus(`${label}のタップを受け付けました。素材を安全確認し、クラウド投入準備をしています…`);
    progress()?.show(stepPayload(1, '操作を受け付けました', {
      title: '✓ 受け付けました', note: '同じボタンの押し直しは不要です。画面操作やタブ移動は可能です。',
    }));
    try {
      progress()?.update(stepPayload(2, `${label}用の素材を確認しています…`, {title: `${label}を準備中`}));
      const prepared = await request('api/cloud-render/prepare-project', {
        method: 'POST', body: form({project, mode}),
      });
      progress()?.update(stepPayload(3, `素材 ${Number(prepared.security?.files || 0)}件を正規化・安全確認しました`, {
        title: '✓ 素材準備完了', note: '実行承認を確認します。',
      }));
      const confirmation = String(prepared.confirmation || '');
      const maxYen = Number(prepared.estimated_max_yen || 0);
      const files = Number(prepared.security?.files || 0);
      const approved = window.confirm(
        `${label}を書き出します。\n\n安全確認済み素材: ${files}件\n費用上限: ${maxYen}円\n承認はこの1回だけ有効です。自動公開は行いません。\n\n「OK」で ${confirmation} を承認します。`
      );
      if (!approved) {
        setLocalStatus(`${label}の実行を取り消しました。Cloud Runは起動していません。`);
        progress()?.finish({title: '実行を取り消しました', stage: 'Cloud Runは起動していません。', step: 3, totalSteps: TOTAL_STEPS});
        setBusy(false);
        return;
      }

      progress()?.update(stepPayload(4, '承認を記録し、Cloud Runへ投入しています…', {title: `${label}を投入中`, note: '投入後も画面操作やタブ移動は可能です。'}));
      setLocalStatus(`${label}の一回承認を確定しています…`);
      await request('api/cloud-render/approve', {
        method: 'POST', body: form({request_id: prepared.request_id, confirmation}),
      });

      setLocalStatus(`${label}をCloud Runへ投入しています…`);
      const dispatched = await request('api/cloud-render/dispatch', {
        method: 'POST', body: form({request_id: prepared.request_id}),
      });
      setLocalStatus(`${label}をCloud Runへ投入しました。\n実行ID: ${dispatched.execution || '確認中'}`);
      progress()?.update(stepPayload(5, '動画を書き出しています…', {
        title: `${label}を処理中`, note: `実行ID: ${dispatched.execution || '確認中'}・画面操作は可能です。`,
      }));
      await pollStatus(prepared.request_id, label);
    } catch (error) {
      const detail = error?.message || error;
      if (activeRequestId && isConnectionError(error)) {
        scheduleReconnect(activeRequestId, activeLabel || label, activeStartedAt || Date.now(), detail);
        return;
      }
      setBusy(false);
      setLocalStatus(`${label}書き出し準備失敗:\n${detail}`);
      progress()?.fail(detail, {title: `${label}書き出し準備に失敗`, step: activeStep, totalSteps: TOTAL_STEPS});
    }
  }

  function delegatedActivation(event) {
    const target = event.target instanceof Element ? event.target.closest('#preview, #final') : null;
    if (!target) return;
    const now = Date.now();
    if (lastActivationId === target.id && now - lastActivationAt < 900) {
      event.preventDefault();
      event.stopImmediatePropagation();
      progress()?.update({title: busy ? 'すでに処理中です' : 'タップを受け付けました', note: busy ? '同じ処理を重複して開始しません。画面操作は可能です。' : ''});
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
