(() => {
  const startButton = document.querySelector('#start');
  const stopButton = document.querySelector('#stop');
  const visualBox = document.querySelector('#visual');
  const clock = document.querySelector('#clock');
  const overlay = document.querySelector('#narrationRecordingOverlay');
  const visualStage = document.querySelector('#narrationRecordingVisual');
  const overlayTop = document.querySelector('#narrationRecordingTop');
  const overlayHelp = overlayTop?.querySelector('.narration-recording-help');
  const overlayBottom = document.querySelector('#narrationRecordingBottom');

  if (
    !startButton || !stopButton || !visualBox || !clock || !overlay ||
    !visualStage || !overlayTop || !overlayBottom
  ) return;

  function findMarker(name) {
    const walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_COMMENT,
    );
    let node = walker.nextNode();
    while (node) {
      if ((node.nodeValue || '').trim() === name) return node;
      node = walker.nextNode();
    }
    return null;
  }

  const visualMarker = findMarker('timed-narration-visual-home');
  const clockMarker = findMarker('timed-narration-clock-home');
  const stopMarker = findMarker('timed-narration-stop-home');

  function restoreAtMarker(element, marker) {
    if (!marker?.parentNode) return;
    marker.parentNode.insertBefore(element, marker.nextSibling);
  }

  function restoreNormalEditor() {
    if (overlay.classList.contains('active')) return;
    restoreAtMarker(visualBox, visualMarker);
    restoreAtMarker(clock, clockMarker);
    restoreAtMarker(stopButton, stopMarker);
  }

  function moveControlsIntoRecordingOverlay() {
    if (visualBox.parentNode !== visualStage) {
      visualStage.appendChild(visualBox);
    }
    if (clock.parentNode !== overlayTop) {
      overlayTop.insertBefore(clock, overlayHelp || null);
    }
    if (stopButton.parentNode !== overlayBottom) {
      overlayBottom.appendChild(stopButton);
    }
  }

  // The original overlay controller created the hidden recording screen and
  // moved these elements into it immediately. Put them back so the user can
  // preview the movie and see the normal timer before recording starts.
  restoreNormalEditor();

  // Move the elements only for the explicit recording-start tap. This capture
  // handler runs before the controller's onclick handler opens the overlay.
  startButton.addEventListener('click', () => {
    if (startButton.disabled) return;
    moveControlsIntoRecordingOverlay();
  }, {capture: true});

  // Permission failures and ordinary recording completion remove the active
  // class. Restore the normal editor even if another handler exits early.
  const observer = new MutationObserver(() => {
    if (!overlay.classList.contains('active')) restoreNormalEditor();
  });
  observer.observe(overlay, {attributes: true, attributeFilter: ['class']});

  window.addEventListener('pageshow', restoreNormalEditor);
})();
