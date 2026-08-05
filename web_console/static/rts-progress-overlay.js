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
    .rts-progress-overlay.visible {
      transform: translateY(0);
      opacity: 1;
      pointer-events: auto;
    }
    .rts-progress-overlay[data-state="failed"] { border: 1px solid rgba(255, 100, 100, .72); }
    .rts-progress-overlay[data-state="completed"] { border: 1px solid rgba(98, 220, 140, .72); }
    .rts-progress-overlay[data-state="stalled"] { border: 1px solid rgba(255, 196, 80, .78); }
    .rts-progress-head { display: flex; gap: 10px; align-items: center; }
    .rts-progress-spinner {
      width: 18px;
      height: 18px;
      flex: 0 0 auto;
      border: 2px solid rgba(255,255,255,.26);
      border-top-color: currentColor;
      border-radius: 50%;
      animation: rts-progress-spin .8s linear infinite;
    }
    [data-state="completed"] .rts-progress-spinner,
    [data-state="failed"] .rts-progress-spinner { animation: none; border: 0; width: auto; height: auto; }
    [data-state="completed"] .rts-progress-spinner::before { content: '✓'; font-weight: 800; }
    [data-state="failed"] .rts-progress-spinner::before { content: '!'; font-weight: 800; }
    .rts-progress-title { font-weight: 750; flex: 1; }
    .rts-progress-stage { margin-top: 7px; color: rgba(255,255,255,.9); }
    .rts-progress-track { height: 7px; margin-top: 10px; border-radius: 999px; overflow: hidden; background: rgba(255,255,255,.14); }
    .rts-progress-bar { height: 100%; width: 16%; border-radius: inherit; background: currentColor; transition: width .25s ease; }
    .rts-progress-bar.indeterminate { animation: rts-progress-slide 1.2s ease-in-out infinite; }
    .rts-progress-meta { display: flex; flex-wrap: wrap; gap: 6px 14px; margin-top: 9px; font-size: 12px; color: rgba(255,255,255,.72); }
    .rts-progress-note { margin-top: 7px; font-size: 12px; color: rgba(255,255,255,.82); }
    @keyframes rts-progress-spin { to { transform: rotate(360deg); } }
    @keyframes rts-progress-slide { 0% { transform: translateX(-120%); } 50% { transform: translateX(260%); } 100% { transform: translateX(-120%); } }
    @media (prefers-reduced-motion: reduce) {
      .rts-progress-spinner, .rts-progress-bar.indeterminate { animation: none; }
    }
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
    <div class="rts-progress-stage"></div>
    <div class="rts-progress-track"><div class="rts-progress-bar indeterminate"></div></div>
    <div class="rts-progress-meta">
      <span class="rts-progress-elapsed">経過 0秒</span>
      <span class="rts-progress-updated">最終更新 0秒前</span>
    </div>
    <div class="rts-progress-note"></div>
  `;
  document.body.appendChild(root);

  const title = root.querySelector('.rts-progress-title');
  const stage = root.querySelector('.rts-progress-stage');
  const bar = root.querySelector('.rts-progress-bar');
  const elapsed = root.querySelector('.rts-progress-elapsed');
  const updated = root.querySelector('.rts-progress-updated');
  const note = root.querySelector('.rts-progress-note');

  let startedAt = 0;
  let updatedAt = 0;
  let timer = 0;
  let hideTimer = 0;
  let active = false;

  const secondsText = value => `${Math.max(0, Math.floor(value / 1000))}秒`;

  function tick() {
    if (!active) return;
    const now = Date.now();
    elapsed.textContent = `経過 ${secondsText(now - startedAt)}`;
    updated.textContent = `最終更新 ${secondsText(now - updatedAt)}前`;
    const silentFor = now - updatedAt;
    if (silentFor >= 120000) root.dataset.state = 'stalled';
    else if (silentFor >= 30000 && root.dataset.state === 'running') root.dataset.state = 'waiting';
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
    setProgress(payload.percent);
    root.classList.add('visible');
    window.clearInterval(timer);
    timer = window.setInterval(tick, 1000);
    tick();
  }

  function setProgress(percent) {
    const numeric = Number(percent);
    if (Number.isFinite(numeric)) {
      bar.classList.remove('indeterminate');
      bar.style.width = `${Math.max(0, Math.min(100, numeric))}%`;
    } else {
      bar.classList.add('indeterminate');
      bar.style.width = '28%';
    }
  }

  function update(payload = {}) {
    if (!active) show(payload);
    updatedAt = Date.now();
    if (payload.state) root.dataset.state = payload.state;
    if (payload.title) title.textContent = payload.title;
    if (payload.stage) stage.textContent = payload.stage;
    if (payload.note !== undefined) note.textContent = payload.note || '';
    if (payload.percent !== undefined) setProgress(payload.percent);
    tick();
  }

  function finish(payload = {}) {
    update({
      state: payload.state || 'completed',
      title: payload.title || '✓ 完了しました',
      stage: payload.stage || '',
      note: payload.note || '',
      percent: 100,
    });
    active = false;
    window.clearInterval(timer);
    if (payload.persist !== true) {
      hideTimer = window.setTimeout(() => root.classList.remove('visible'), payload.hideAfter ?? 4500);
    }
  }

  function fail(message, payload = {}) {
    finish({
      state: 'failed',
      title: payload.title || '処理に失敗しました',
      stage: String(message || '不明なエラー'),
      note: payload.note || '内容を確認してから再実行してください。',
      persist: true,
    });
  }

  window.RTSProgressOverlay = {show, update, finish, fail};
})();
