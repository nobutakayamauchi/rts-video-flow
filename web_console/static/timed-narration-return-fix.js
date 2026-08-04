(() => {
  const returnLink = document.querySelector('#skip');
  const topBackLink = document.querySelector('#back');
  if (!returnLink) return;

  const style = document.createElement('style');
  style.dataset.timedNarrationReturnFix = 'v3';
  style.textContent = `
    #skip.saved-return {
      pointer-events: auto !important;
      opacity: 1 !important;
      touch-action: manipulation;
    }
  `;
  document.head.appendChild(style);

  const params = new URLSearchParams(window.location.search);
  const projectName = params.get('project') || '';
  const returnUrl = `../?project=${encodeURIComponent(projectName)}`;

  function isSavedReturn() {
    return returnLink.classList.contains('saved-return') ||
      returnLink.textContent.trim() === '構成へ戻る';
  }

  function enableReturnNavigation() {
    if (!isSavedReturn()) return;

    // Only mutate values that actually differ. The previous implementation
    // observed style/aria changes and rewrote those same attributes, causing an
    // endless MutationObserver loop in iPhone Safari after a successful save.
    if (returnLink.classList.contains('saving-lock')) {
      returnLink.classList.remove('saving-lock');
    }
    if (returnLink.hasAttribute('aria-disabled')) {
      returnLink.removeAttribute('aria-disabled');
    }
    if (returnLink.style.pointerEvents !== 'auto') {
      returnLink.style.pointerEvents = 'auto';
    }
    if (returnLink.getAttribute('href') !== returnUrl) {
      returnLink.setAttribute('href', returnUrl);
    }
    if (returnLink.getAttribute('role') !== 'button') {
      returnLink.setAttribute('role', 'button');
    }
    if (topBackLink && topBackLink.getAttribute('href') !== returnUrl) {
      topBackLink.setAttribute('href', returnUrl);
    }
  }

  const observer = new MutationObserver(() => {
    if (!isSavedReturn()) return;
    enableReturnNavigation();
    observer.disconnect();
  });
  observer.observe(returnLink, {
    attributes: true,
    attributeFilter: ['class'],
    childList: true,
    subtree: true,
  });

  function navigateToComposition(event) {
    if (!isSavedReturn()) return;
    event.preventDefault();
    event.stopPropagation();
    enableReturnNavigation();
    window.location.href = returnUrl;
  }

  returnLink.addEventListener('click', navigateToComposition, {capture: true});
  returnLink.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') navigateToComposition(event);
  }, {capture: true});

  topBackLink?.addEventListener('click', event => {
    event.preventDefault();
    window.location.href = returnUrl;
  }, {capture: true});

  enableReturnNavigation();
})();
