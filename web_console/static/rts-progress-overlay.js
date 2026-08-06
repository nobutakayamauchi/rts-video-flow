(() => {
  if (window.RTSProgressOverlay) return;

  const style = document.createElement('style');
  style.dataset.rtsProgressOverlay = 'v1';
  style.textContent = `
    .rts-progress-overlay {
      position: fixed;
      left: max(12px, env(safe-area-inset-left));
      right: max(12px, env(safe-area-inset-right));
      bottom: max(12px, env(safe-area-inset-bottom));
      z-index: 2147483000;
      max-width: 720px;
      margin: 0 auto;
      padding: 14px 16px;
      border-radius: 16px;
      background: rgba(20, 20, 24, .96);
      color: #fff;
      box-shadow: 0 12px 36px rgba(0, 0, 0, .38);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
      transform: translateY(calc(100% + 40px));
      opacity: 0;
      pointer-events: none;
      transition: transform .18s ease, opacity .18s ease;
    }
    .rts-progress-overlay.visible { transform: translateY(0); opacity: 1; pointer-events: none; }
    .rts-progress-overlay[data-state="failed"] { border: 1px solid rgba(255, 100, 100, .72); }
    .rts-progress-overlay[data-state="completed"] { border: 1px solid rgba(98, 220, 140, .72); }
    .rts-progress-overlay[data-state="stalled"],
    .rts-progress-overlay[data-state="reconnecting"] { border: 1px solid rgba(255, 196, 80, .78); }
    .rts-progress-head { display: flex; gap: 10px; align-items: center; }
    .rts-progress-spinner { width: 18px; height: 18px; flex: 0 0 auto; border: 2px solid rgba(255,255,255,.26); border-top-color: currentColor; border-radius: 50%; animation: rts-progress-spin .8s linear infinite; }
    [data-state="completed"] .rts-progress-spinner,
    [data-state="failed"] .rts-progress-spinner { animation: none; border: 0; width: auto; height: auto; }
    [data-state="completed"] .rts-progress-spinner::before { content: '✓'; font-weight: 800; }
    [data-state="failed"] .rts-progress-spinner::before { content: '!'; font-weight: 800; }
    .rts-progress-title { font-weight: 750; flex: 1; }
    .rts-progress-step { margin-top: 7px; font-weight: 800; color: #ffd15a; }
    .rts-progress-stage { margin-top: 2px; color: rgba(255,255,255,.9); }
    .rts-progress-track { height: 7px; margin-top: 10px; border-radius: 999px; overflow: hidden; background: rgba(255,255,255,.14); }
    .rts-progress-bar { height: 100%; width: 0; border-radius: inherit; background: currentColor; transition: width .25s ease; }
    .rts-progress-meta { display: flex; flex-wrap: wrap; gap: 6px 14px; margin-top: 9px; font-size: 12px; color: rgba(255,255,255,.72); }
    .rts-progress-note { margin-top: 7px; font-size: 12px; color: rgba(255,255,255,.82); }
    .rts-progress-action { display: none; width: 100%; margin-top: 10px; min-height: 42px; border: 1px solid rgba(255,255,255,.32); border-radius: 10px; background: rgba(255,255,255,.10); color: inherit; font: inherit; font-weight: 750; pointer-events: auto; touch-action: manipulation; }
    .rts-progress-action.visible { display: block; }
    @keyframes rts-progress-spin { to { transform: rotate(360deg); } }
    @media (prefers-reduced-motion: reduce) { .rts-progress-spinner { animation: none; } }
  `;
  document.head.appendChild(style);

  const root = document.createElement('section');
  root.className = 'rts-progress-overlay';
  root.setAttribute('role', 'status');
  root.setAttribute('aria-live', 'polite');
  root.innerHTML = `
    <div class="rts-progress-head">
      <span class="rts-progress-spinner" aria-hidden="true"></span>
      <strong class="rts-progress-title">処理を受け付けました</strong>
    </div>
    <div class="rts-progress-step">工程 1 / 7</div>
    <div class="rts-progress-stage"></div>
    <div class="rts-progress-track"><div class="rts-progress-bar"></div></div>
    <div class="rts-progress-meta">
      <span class="rts-progress-elapsed">経過 0秒</span>
      <span class="rts-progress-updated">最終更新 0秒前</span>
    </div>
    <div class="rts-progress-note"></div>
    <button type="button" class="rts-progress-action">状態確認を再開</button>
  `;
  document.body.appendChild(root);

  const title = root.querySelector('.rts-progress-title');
  const step = root.querySelector('.rts-progress-step');
  const stage = root.querySelector('.rts-progress-stage');
  const bar = root.querySelector('.rts-progress-bar');
  const elapsed = root.querySelector('.rts-progress-elapsed');
  const updated = root.querySelector('.rts-progress-updated');
  const note = root.querySelector('.rts-progress-note');
  const action = root.querySelector('.rts-progress-action');

  let startedAt = 0;
  let updatedAt = 0;
  let timer = 0;
  let hideTimer = 0;
  let active = false;
  let actionHandler = null;
  let currentStep = 1;
  let totalSteps = 7;

  const secondsText = value => `${Math.max(0, Math.floor(value / 1000))}秒`;

  function tick() {
    if (!active) return;
    const now = Date.now();
    elapsed.textContent = `経過 ${secondsText(now - startedAt)}`;
    updated.textContent = `最終更新 ${secondsText(now - updatedAt)}前`;
    const silentFor = now - updatedAt;
    if (silentFor >= 120000 && root.dataset.state === 'running') root.dataset.state = 'stalled';
    else if (silentFor >= 30000 && root.dataset.state === 'running') root.dataset.state = 'waiting';
  }

  function setAction(label, handler) {
    actionHandler = typeof handler === 'function' ? handler : null;
    action.textContent = label || '状態確認を再開';
    action.classList.toggle('visible', Boolean(actionHandler));
  }

  action.addEventListener('click', event => {
    event.preventDefault();
    event.stopPropagation();
    actionHandler?.();
  });

  function setStep(value, total = totalSteps) {
    const numericTotal = Math.max(1, Number(total) || 7);
    const numericStep = Math.max(0, Math.min(numericTotal, Number(value) || 0));
    currentStep = numericStep;
    totalSteps = numericTotal;
    step.textContent = `工程 ${numericStep} / ${numericTotal}`;
    setProgress((numericStep / numericTotal) * 100);
  }

  function show(payload = {}) {
    window.clearTimeout(hideTimer);
    active = true;
    startedAt = payload.startedAt || Date.now();
    updatedAt = Date.now();
    root.dataset.state = payload.state || 'running';
    title.textContent = payload.title || '✓ 受け付けました';
    stage.textContent = payload.stage || '処理を開始しています…';
    note.textContent = payload.note || '';
    setAction(payload.actionLabel, payload.onAction);
    setStep(payload.step ?? 1, payload.totalSteps ?? 7);
    root.classList.add('visible');
    window.clearInterval(timer);
    timer = window.setInterval(tick, 1000);
    tick();
  }

  function setProgress(percent) {
    const numeric = Number(percent);
    bar.style.width = `${Math.max(0, Math.min(100, Number.isFinite(numeric) ? numeric : 0))}%`;
  }

  function update(payload = {}) {
    if (!active) show(payload);
    updatedAt = Date.now();
    if (payload.state) root.dataset.state = payload.state;
    if (payload.title) title.textContent = payload.title;
    if (payload.stage) stage.textContent = payload.stage;
    if (payload.note !== undefined) note.textContent = payload.note || '';
    if (payload.step !== undefined || payload.totalSteps !== undefined) setStep(payload.step ?? currentStep, payload.totalSteps ?? totalSteps);
    else if (payload.percent !== undefined) setProgress(payload.percent);
    if (payload.onAction !== undefined || payload.actionLabel !== undefined) setAction(payload.actionLabel, payload.onAction);
    tick();
  }

  function finish(payload = {}) {
    update({
      state: payload.state || 'completed',
      title: payload.title || '✓ 完了しました',
      stage: payload.stage || '',
      note: payload.note || '',
      step: payload.step ?? totalSteps,
      totalSteps: payload.totalSteps ?? totalSteps,
      onAction: null,
    });
    active = false;
    window.clearInterval(timer);
    if (payload.persist !== true) hideTimer = window.setTimeout(() => root.classList.remove('visible'), payload.hideAfter ?? 4500);
  }

  function fail(message, payload = {}) {
    update({
      state: 'failed',
      title: payload.title || '処理に失敗しました',
      stage: String(message || '不明なエラー'),
      note: payload.note || '内容を確認してから再実行してください。',
      step: payload.step ?? currentStep,
      totalSteps: payload.totalSteps ?? totalSteps,
      onAction: payload.onAction,
      actionLabel: payload.actionLabel,
    });
    active = false;
    window.clearInterval(timer);
  }

  window.RTSProgressOverlay = {show, update, finish, fail, setAction, setStep};
})();
