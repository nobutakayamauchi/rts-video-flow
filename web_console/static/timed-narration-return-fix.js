(() => {
  const returnLink = document.querySelector('#skip');
  const topBackLink = document.querySelector('#back');
  if (!returnLink) return;

  const style = document.createElement('style');
  style.dataset.timedNarrationReturnFix = 'v2';
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
    returnLink.classList.remove('saving-lock');
    returnLink.removeAttribute('aria-disabled');
    returnLink.style.pointerEvents = 'auto';
    returnLink.href = returnUrl;
    returnLink.setAttribute('role', 'button');
    if (topBackLink) topBackLink.href = returnUrl;
  }

  const observer = new MutationObserver(enableReturnNavigation);
  observer.observe(returnLink, {
    attributes: true,
    attributeFilter: ['class', 'aria-disabled', 'style'],
    childList: true,
    subtree: true,
  });

  function navigateToComposition(event) {
    enableReturnNavigation();
    if (!isSavedReturn()) return;
    event.preventDefault();
    event.stopPropagation();
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
