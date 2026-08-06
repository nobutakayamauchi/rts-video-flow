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

  function outputPage(mode, requestId) {
    const url = new URL('static/output.html', new URL('./', location.href));
    url.searchParams.set('project', projectValue());
    url.searchParams.set('completed', mode);
    if (requestId) url.searchParams.set('request', requestId);
    return url.toString();
  }

  function goToCompletedOutput(mode, requestId) {
    window.setTimeout(() => {
      location.assign(outputPage(mode, requestId));
    }, 900);
  }

  function scheduleReconnect(requestId, label, startedAt, detail) {
    reconnectAttempts += 1;
    const delay = reconnectDelay(reconnectAttempts);
    const seconds = Math.round(delay / 1000);
    setLocalStatus(`${label}は処理を継続中です。通信だけ切れたため、状態確認を再接続します。`);
    progress()?.update(stepPayload(activeStep, `工程 ${activeStep}/${TOTAL_STEPS}・${seconds}秒後に再確認`, {
      state: 'reconnecting',
      title: '通信を再接続中',
      note: 'Cloud Runの処理は継続中です。画面操作やタブ移動も可能です。',
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
      progress()?.update(stepPayload(activeStep, `工程 ${activeStep}/${TOTAL_STEPS}・状態を確認しています…`, {
        state: 'reconnecting', title: '再接続中', note: 'Cloud Run側の処理状態を確認しています。', onAction: null,
      }));
    }
    try {
      const record = await request(`api/cloud-render/status/${encodeURIComponent(requestId)}`, {cache: 'no-store'});
      reconnectAttempts = 0;
      const execution = record.execution ? `\n実行ID: ${record.execution}` : '';
      if (record.status === 'COMPLETED') {
        progress()?.update(stepPayload(6, '工程 6/7・完成ファイルを確認しています…', {
          title: `${label}の完成確認中`, state: 'running', note: record.output_uri || '',
        }));
        setLocalStatus(`${label}のクラウド書き出しが完了しました。\n確認画面へ移動します。`);
        progress()?.finish({
          title: '✓ 書き出し完了',
          stage: '工程 7/7・確認画面へ移動します',
          note: label === 'プレビュー' ? '内容を確認し、問題なければ最終版へ進んでください。' : '最終版を確認して保存してください。',
          step: 7,
          totalSteps: TOTAL_STEPS,
          hideAfter: 1800,
        });
        setBusy(false);
        activeRequestId = '';
        if (typeof load === 'function') await load();
        goToCompletedOutput(record.mode || (label === 'プレビュー' ? 'preview' : 'final'), requestId);
        return;
      }
      if (record.status === 'FAILED' || record.status === 'REJECTED') {
        throw new Error(record.error || `クラウド書き出しが${record.status}になりました`);
      }

      activeStep = 5;
      const stage = `工程 5/${TOTAL_STEPS}・動画を書き出しています（${record.status}）`;
      setLocalStatus(`${label}をCloud Runで処理中です。状態: ${record.status}${execution}`);
      progress()?.update(stepPayload(5, stage, {
        state: Date.now() - startedAt > 10 * 60 * 1000 ? 'waiting' : 'running',
        title: `${label}を処理中`,
        note: record.execution ? `実行ID: ${record.execution}・残り2工程` : '残り2工程・画面操作は可能です。',
        onAction: null,
      }));
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
      progress()?.fail(detail, {
        title: `${label}の状態確認に失敗`,
        step: activeStep,
        totalSteps: TOTAL_STEPS,
        note: 'エラー内容をコピーしてAIへ渡せます。画面操作やタブ移動は可能です。',
        onAction: () => pollStatus(requestId, label, startedAt, true),
        actionLabel: '状態を再確認',
      });
    }
  }

  async function cloudRender(mode) {
    if (busy) {
      progress()?.update({title: 'すでに処理中です', note: `工程 ${activeStep}/${TOTAL_STEPS}・同じ処理を重複して開始しません。`});
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
    progress()?.show(stepPayload(1, '工程 1/7・操作を受け付けました', {
      title: '✓ 受け付けました', note: '押し直しは不要です。残り6工程です。',
    }));
    try {
      progress()?.update(stepPayload(2, `工程 2/7・${label}用の素材を確認しています…`, {title: `${label}を準備中`, note: '残り5工程'}));
      const prepared = await request('api/cloud-render/prepare-project', {
        method: 'POST', body: form({project, mode}),
      });
      progress()?.update(stepPayload(3, `工程 3/7・素材 ${Number(prepared.security?.files || 0)}件を正規化・安全確認済み`, {
        title: '✓ 素材準備完了', note: '残り4工程・実行承認を確認します。',
      }));
      const confirmation = String(prepared.confirmation || '');
      const maxYen = Number(prepared.estimated_max_yen || 0);
      const files = Number(prepared.security?.files || 0);
      const approved = window.confirm(
        `${label}を書き出します。\n\n安全確認済み素材: ${files}件\n費用上限: ${maxYen}円\n承認はこの1回だけ有効です。自動公開は行いません。\n\n「OK」で ${confirmation} を承認します。`
      );
      if (!approved) {
        setLocalStatus(`${label}の実行を取り消しました。Cloud Runは起動していません。`);
        progress()?.finish({title: '実行を取り消しました', stage: '工程 3/7で停止・Cloud Runは未起動', step: 3, totalSteps: TOTAL_STEPS});
        setBusy(false);
        return;
      }

      progress()?.update(stepPayload(4, '工程 4/7・承認を記録しCloud Runへ投入しています…', {
        title: `${label}を投入中`, note: '残り3工程・投入後も画面操作やタブ移動は可能です。',
      }));
      setLocalStatus(`${label}の一回承認を確定しています…`);
      await request('api/cloud-render/approve', {
        method: 'POST', body: form({request_id: prepared.request_id, confirmation}),
      });

      setLocalStatus(`${label}をCloud Runへ投入しています…`);
      const dispatched = await request('api/cloud-render/dispatch', {
        method: 'POST', body: form({request_id: prepared.request_id}),
      });
      setLocalStatus(`${label}をCloud Runへ投入しました。\n実行ID: ${dispatched.execution || '確認中'}`);
      progress()?.update(stepPayload(5, '工程 5/7・動画を書き出しています…', {
        title: `${label}を処理中`, note: `残り2工程・実行ID: ${dispatched.execution || '確認中'}`,
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
      progress()?.fail(detail, {
        title: `${label}書き出し準備に失敗`,
        step: activeStep,
        totalSteps: TOTAL_STEPS,
        note: 'エラー内容をコピーしてAIへ渡せます。画面操作やタブ移動は可能です。',
      });
    }
  }

  function delegatedActivation(event) {
    const target = event.target instanceof Element ? event.target.closest('#preview, #final') : null;
    if (!target) return;
    const now = Date.now();
    if (lastActivationId === target.id && now - lastActivationAt < 900) {
      event.preventDefault();
      event.stopImmediatePropagation();
      progress()?.update({title: busy ? 'すでに処理中です' : 'タップを受け付けました', note: busy ? `工程 ${activeStep}/${TOTAL_STEPS}・重複実行しません。` : ''});
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
