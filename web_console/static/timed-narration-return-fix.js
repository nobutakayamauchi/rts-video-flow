(() => {
  const returnLink = document.querySelector('#skip');
  const topBackLink = document.querySelector('#back');
  if (!returnLink) return;

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
    if (topBackLink) topBackLink.href = returnUrl;
  }

  const observer = new MutationObserver(enableReturnNavigation);
  observer.observe(returnLink, {
    attributes: true,
    attributeFilter: ['class', 'aria-disabled', 'style'],
    childList: true,
    subtree: true,
  });

  returnLink.addEventListener('click', event => {
    enableReturnNavigation();
    if (!isSavedReturn()) return;
    event.preventDefault();
    window.location.assign(returnUrl);
  }, {capture: true});

  topBackLink?.addEventListener('click', event => {
    event.preventDefault();
    window.location.assign(returnUrl);
  }, {capture: true});

  enableReturnNavigation();
})();
