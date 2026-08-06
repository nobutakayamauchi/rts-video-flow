(() => {
  const params = new URLSearchParams(location.search);
  const completed = params.get('completed');
  if (!completed) return;

  const $ = selector => document.querySelector(selector);
  const project = params.get('project') || $('#project')?.value || '';
  const encodedProject = encodeURIComponent(project);
  const previewButton = $('#preview');
  const finalButton = $('#final');
  const status = $('#status');
  const previewPanel = $('#previewInfo')?.closest('.panel');
  const finalPanel = $('#finalInfo')?.closest('.panel');
  const operationPanel = previewButton?.closest('.panel');
  const appRoot = new URL('../', location.href);
  const apiUrl = path => new URL(String(path).replace(/^\/+/, ''), appRoot).toString();

  const style = document.createElement('style');
  style.textContent = `
    html,body{min-height:100%;background:#0b0f14;overscroll-behavior-y:none}
    body{min-height:100dvh}
    .wrap{padding-bottom:calc(220px + env(safe-area-inset-bottom))!important}
    #back,#trash{position:relative;z-index:2;display:inline-block;min-height:44px;padding:10px 4px;touch-action:manipulation;cursor:pointer}
    .rts-review-banner{border:1px solid #ffc84a;background:#171d26;border-radius:16px;padding:16px;margin:14px 0}
    .rts-review-banner h2{margin:0 0 8px;color:#ffc84a}
    .rts-review-banner p{margin:6px 0;line-height:1.55}
    .rts-review-banner .button{margin-top:14px}
    .rts-review-target{outline:2px solid #ffc84a;outline-offset:3px}
    .rts-review-actions{display:grid!important;grid-template-columns:1fr!important;gap:10px}
    @media(max-width:450px){.wrap{padding-left:15px;padding-right:15px}}
  `;
  document.head.appendChild(style);

  function forceNavigation(element, url) {
    if (!element) return;
    element.href = url;
    element.removeAttribute('target');
    element.addEventListener('click', event => {
      event.preventDefault();
      window.location.assign(url);
    });
  }

  forceNavigation($('#back'), `../?project=${encodedProject}`);
  forceNavigation($('#trash'), `trash.html?project=${encodedProject}`);

  const banner = document.createElement('section');
  banner.className = 'rts-review-banner';
  operationPanel?.parentNode?.insertBefore(banner, operationPanel);
  operationPanel?.querySelector('.row')?.classList.add('rts-review-actions');

  function markTarget(panel) {
    panel?.classList.add('rts-review-target');
  }

  if (completed === 'preview') {
    const previewUrl = apiUrl(`api/output-file/${encodedProject}/preview.mp4`);
    banner.innerHTML = `
      <h2>プレビューが完成しました</h2>
      <p>まず動画を確認してください。問題がなければ下の「OK・最終版を書き出す」へ進みます。</p>
      <a class="button secondary" href="${previewUrl}">プレビューを再生して確認</a>
      <p>修正する場合は「構成へ戻る」を使います。</p>
    `;
    if (status) status.textContent = 'プレビュー完成。内容を確認してください。';
    if (previewButton) previewButton.hidden = true;
    if (finalButton) {
      finalButton.hidden = false;
      finalButton.textContent = 'OK・最終版を書き出す';
      finalButton.classList.remove('secondary');
    }
    markTarget(previewPanel);
  }

  if (completed === 'final') {
    const finalUrl = apiUrl(`api/download/${encodedProject}`);
    banner.innerHTML = `
      <h2>最終版が完成しました</h2>
      <p>完成動画を確認し、保存ボタンから端末の保存先を選んでください。</p>
      <a class="button secondary" href="${finalUrl}" download="${project || 'rts-video'}.mp4">保存先を選んで保存</a>
    `;
    if (status) status.textContent = '最終版完成。確認して保存してください。';
    if (previewButton) previewButton.hidden = true;
    if (finalButton) finalButton.hidden = true;
    markTarget(finalPanel);
  }

  const observer = new MutationObserver(() => {
    if (completed === 'preview') {
      const link = $('#previewInfo a.button');
      if (link) {
        link.textContent = 'プレビューを再生して確認';
        link.removeAttribute('target');
      }
    }
    if (completed === 'final') {
      const link = $('#finalInfo a.button');
      if (link) {
        link.textContent = '保存先を選んで保存';
        link.removeAttribute('target');
        link.setAttribute('download', `${project || 'rts-video'}.mp4`);
      }
    }
  });
  observer.observe(document.body, {subtree: true, childList: true});
})();
