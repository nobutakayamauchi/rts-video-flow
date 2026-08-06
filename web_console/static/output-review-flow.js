(() => {
  const params = new URLSearchParams(location.search);
  const completed = params.get('completed');
  if (!completed) return;

  const $ = selector => document.querySelector(selector);
  const project = params.get('project') || $('#project')?.value || '';
  const previewButton = $('#preview');
  const finalButton = $('#final');
  const status = $('#status');
  const previewPanel = $('#previewInfo')?.closest('.panel');
  const finalPanel = $('#finalInfo')?.closest('.panel');

  const style = document.createElement('style');
  style.textContent = `
    .rts-review-banner{border:1px solid #ffc84a;background:#171d26;border-radius:16px;padding:16px;margin:14px 0}
    .rts-review-banner h2{margin:0 0 8px;color:#ffc84a}
    .rts-review-banner p{margin:6px 0;line-height:1.55}
    .rts-review-target{outline:2px solid #ffc84a;outline-offset:3px}
  `;
  document.head.appendChild(style);

  const banner = document.createElement('section');
  banner.className = 'rts-review-banner';
  const operationPanel = previewButton?.closest('.panel');
  operationPanel?.parentNode?.insertBefore(banner, operationPanel);

  function openTarget(panel) {
    window.setTimeout(() => {
      panel?.classList.add('rts-review-target');
      panel?.scrollIntoView({behavior: 'smooth', block: 'center'});
    }, 350);
  }

  if (completed === 'preview') {
    banner.innerHTML = `
      <h2>プレビューが完成しました</h2>
      <p>動画を確認し、問題がなければ最終版へ進んでください。</p>
      <p>修正する場合は「構成へ戻る」を使います。</p>
    `;
    if (status) status.textContent = 'プレビュー完成。内容を確認してください。';
    if (previewButton) previewButton.hidden = true;
    if (finalButton) {
      finalButton.hidden = false;
      finalButton.textContent = 'OK・最終版を書き出す';
      finalButton.classList.remove('secondary');
    }
    openTarget(previewPanel);
  }

  if (completed === 'final') {
    banner.innerHTML = `
      <h2>最終版が完成しました</h2>
      <p>完成動画を確認し、保存ボタンから端末の保存先を選んでください。</p>
    `;
    if (status) status.textContent = '最終版完成。確認して保存してください。';
    if (previewButton) previewButton.hidden = true;
    if (finalButton) finalButton.hidden = true;
    openTarget(finalPanel);
  }

  const observer = new MutationObserver(() => {
    if (completed === 'preview') {
      const link = $('#previewInfo a.button');
      if (link) link.textContent = 'プレビューを再生して確認';
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
