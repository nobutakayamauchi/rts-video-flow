(() => {
  const bar = document.querySelector('.global');
  const applyButton = document.querySelector('#apply');
  const previewButton = document.querySelector('#preview');
  const finalButton = document.querySelector('#final');
  const openFinalLink = document.querySelector('#openFinal');
  const statusBox = document.querySelector('#status');

  if (!bar || !applyButton || !previewButton || !finalButton || !openFinalLink) return;

  const style = document.createElement('style');
  style.dataset.composeControlsRecovery = 'v1';
  style.textContent = `
    .global {
      z-index: 10000 !important;
      pointer-events: auto !important;
      isolation: isolate;
    }
    .global-inner,
    .global-inner > button,
    .global-inner > a {
      pointer-events: auto !important;
      touch-action: manipulation;
      -webkit-tap-highlight-color: rgba(255, 200, 74, .22);
    }
    .global-inner > button,
    .global-inner > a {
      position: relative;
      z-index: 1;
      min-height: 48px;
    }
    .global.compose-busy .global-inner > * {
      opacity: .62;
    }
  `;
  document.head.appendChild(style);

  let busy = false;
  let lastTouchAt = 0;

  function setLocalStatus(message) {
    if (typeof setStatus === 'function') setStatus(message);
    else if (statusBox) statusBox.textContent = message;
  }

  async function runOnce(label, action) {
    if (busy) return;
    busy = true;
    bar.classList.add('compose-busy');
    try {
      await action();
    } catch (error) {
      setLocalStatus(`${label}失敗: ${error?.message || error}`);
    } finally {
      busy = false;
      bar.classList.remove('compose-busy');
    }
  }

  function bindControl(element, handler) {
    const invoke = event => {
      if (event.type === 'touchend') lastTouchAt = Date.now();
      if (event.type === 'click' && Date.now() - lastTouchAt < 700) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      handler();
    };
    element.addEventListener('touchend', invoke, {capture: true, passive: false});
    element.addEventListener('click', invoke, {capture: true});
  }

  bindControl(applyButton, () => runOnce('変更反映', async () => {
    setLocalStatus('変更内容を再読み込みしています…');
    if (typeof load !== 'function') throw new Error('構成の再読み込み処理が見つかりません');
    await load();
  }));

  bindControl(previewButton, () => runOnce('プレビュー書き出し', async () => {
    if (typeof renderOutput !== 'function') throw new Error('書き出し処理が見つかりません');
    await renderOutput('preview');
  }));

  bindControl(finalButton, () => runOnce('最終版書き出し', async () => {
    if (typeof renderOutput !== 'function') throw new Error('書き出し処理が見つかりません');
    await renderOutput('final');
  }));

  bindControl(openFinalLink, () => {
    const href = openFinalLink.href;
    if (!href) {
      setLocalStatus('完成動画のURLがまだありません。先に「最終版を書き出す」を実行してください。');
      return;
    }
    window.location.assign(href);
  });
})();
