(() => {
  const startButton = document.querySelector('#start');
  const stopButton = document.querySelector('#stop');
  const visualBox = document.querySelector('#visual');
  const clock = document.querySelector('#clock');
  const recordStatus = document.querySelector('#recordStatus');

  if (!startButton || !stopButton || !visualBox || !clock || !recordStatus) return;

  const style = document.createElement('style');
  style.dataset.timedNarrationRecordingOverlay = 'v1';
  style.textContent = `
    body.narration-recording-active {
      overflow: hidden;
    }
    #narrationRecordingOverlay {
      display: none;
    }
    #narrationRecordingOverlay.active {
      position: fixed;
      inset:
        max(8px, env(safe-area-inset-top))
        max(8px, env(safe-area-inset-right))
        max(8px, env(safe-area-inset-bottom))
        max(8px, env(safe-area-inset-left));
      z-index: 2000;
      display: grid;
      grid-template-rows: auto minmax(0, 1fr) auto;
      overflow: hidden;
      border: 3px solid #ff6b63;
      border-radius: 20px;
      background: #000;
      box-shadow: 0 18px 70px rgba(0, 0, 0, .78);
    }
    .narration-recording-overlay-bar {
      position: relative;
      z-index: 3;
      color: #fff;
      background: rgba(12, 15, 20, .72);
      -webkit-backdrop-filter: blur(12px);
      backdrop-filter: blur(12px);
    }
    #narrationRecordingTop {
      padding: 11px 13px 10px;
      border-bottom: 1px solid rgba(255,255,255,.2);
    }
    .narration-recording-heading {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      font-weight: 950;
    }
    .narration-recording-dot {
      display: inline-block;
      width: 13px;
      height: 13px;
      margin-right: 7px;
      border-radius: 50%;
      background: #ff3b30;
      box-shadow: 0 0 0 5px rgba(255, 59, 48, .2);
      animation: narration-recording-pulse 1s infinite;
    }
    #narrationRecordingTop #clock {
      width: auto;
      min-width: 152px;
      margin: 9px 0 0;
      padding: 8px 10px;
      border-color: rgba(255,255,255,.24);
      font-size: 1.55rem;
      background: rgba(0,0,0,.38);
    }
    .narration-recording-help {
      margin: 7px 0 0;
      color: #ffe7a8;
      font-size: .86rem;
      line-height: 1.45;
    }
    #narrationRecordingVisual {
      min-height: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      background: #000;
    }
    #narrationRecordingVisual #visual {
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    #narrationRecordingVisual video,
    #narrationRecordingVisual img {
      display: block;
      width: 100%;
      height: 100%;
      max-height: none;
      margin: 0;
      border-radius: 0;
      object-fit: contain;
      background: #000;
    }
    #narrationRecordingBottom {
      padding: 10px 11px calc(10px + env(safe-area-inset-bottom));
      border-top: 1px solid rgba(255,255,255,.2);
    }
    #narrationRecordingBottom .narration-recording-state {
      margin: 0 0 8px;
      text-align: center;
      color: #ffd8d5;
      font-size: .9rem;
      font-weight: 900;
    }
    #narrationRecordingBottom #stop {
      min-height: 58px;
      margin: 0;
      font-size: 1.08rem;
      opacity: 1;
      touch-action: manipulation;
    }
    #narrationRecordingBottom #stop:disabled {
      opacity: .58;
    }
    @keyframes narration-recording-pulse { 50% { opacity: .45; } }
    @media (max-width: 430px) {
      #narrationRecordingOverlay.active { border-radius: 16px; }
      #narrationRecordingTop { padding: 9px 10px 8px; }
      #narrationRecordingTop #clock { font-size: 1.35rem; }
      .narration-recording-help { font-size: .8rem; }
    }
  `;
  document.head.appendChild(style);

  startButton.textContent = '● 映像を見ながら録音';

  const visualMarker = document.createComment('timed-narration-visual-home');
  visualBox.parentNode?.insertBefore(visualMarker, visualBox);
  const clockMarker = document.createComment('timed-narration-clock-home');
  clock.parentNode?.insertBefore(clockMarker, clock);
  const stopMarker = document.createComment('timed-narration-stop-home');
  stopButton.parentNode?.insertBefore(stopMarker, stopButton);

  const overlay = document.createElement('div');
  overlay.id = 'narrationRecordingOverlay';
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.setAttribute('aria-label', '映像を見ながら後入れ音声を録音');

  const top = document.createElement('div');
  top.id = 'narrationRecordingTop';
  top.className = 'narration-recording-overlay-bar';

  const heading = document.createElement('div');
  heading.className = 'narration-recording-heading';
  heading.innerHTML = '<span><span class="narration-recording-dot" aria-hidden="true"></span>後入れ音声</span><span id="narrationRecordingMode">マイク準備中</span>';

  const help = document.createElement('p');
  help.className = 'narration-recording-help';
  help.textContent = '元動画は無音で先頭から再生します。映像終了後も録音は続き、最後の画面で超過時間を確認できます。';

  top.append(heading, clock, help);

  const visualStage = document.createElement('div');
  visualStage.id = 'narrationRecordingVisual';
  visualStage.appendChild(visualBox);

  const bottom = document.createElement('div');
  bottom.id = 'narrationRecordingBottom';
  bottom.className = 'narration-recording-overlay-bar';

  const stateText = document.createElement('p');
  stateText.className = 'narration-recording-state';
  stateText.textContent = 'マイクの準備ができると、映像と録音が同時に始まります';
  bottom.append(stateText, stopButton);

  overlay.append(top, visualStage, bottom);
  document.body.appendChild(overlay);

  const originalStart = startButton.onclick;
  const originalStop = stopButton.onclick;
  let active = false;
  let recordingObserved = false;
  let monitorFrame = 0;
  let visualWasMuted = false;
  let visualHadControls = false;

  function restoreAtMarker(element, marker) {
    marker.parentNode?.insertBefore(element, marker.nextSibling);
  }

  function currentVisual() {
    return visualBox.querySelector('video, img');
  }

  function prepareVisual() {
    const visual = currentVisual();
    if (!(visual instanceof HTMLVideoElement)) return;
    visual.pause();
    try { visual.currentTime = 0; } catch {}
    visualWasMuted = visual.muted;
    visualHadControls = visual.controls;
    visual.muted = true;
    visual.controls = false;
  }

  async function startVisualPlayback() {
    const visual = currentVisual();
    if (!(visual instanceof HTMLVideoElement)) return;
    try {
      visual.currentTime = 0;
      visual.muted = true;
      await visual.play();
    } catch (error) {
      recordStatus.textContent = `録音は開始しましたが、映像を自動再生できませんでした: ${error.message}`;
    }
  }

  function freezeVisualAtEnd() {
    const visual = currentVisual();
    if (!(visual instanceof HTMLVideoElement)) return;
    visual.pause();
    const duration = Number(visual.duration);
    if (Number.isFinite(duration) && duration > .05) {
      try { visual.currentTime = Math.max(0, duration - .04); } catch {}
    }
  }

  function monitorRecording() {
    if (!active) return;

    if (recorder?.state === 'recording') {
      if (!recordingObserved) {
        recordingObserved = true;
        const mode = document.querySelector('#narrationRecordingMode');
        if (mode) mode.textContent = '録音中';
        stateText.textContent = '映像を見ながら話してください。0秒を過ぎても録音は続きます。';
        startVisualPlayback();
      }

      const visual = currentVisual();
      if (visual instanceof HTMLVideoElement) {
        const target = Number(currentTarget());
        if (visual.ended || (Number.isFinite(target) && visual.currentTime >= target - .03)) {
          freezeVisualAtEnd();
        }
      }
    } else if (recordingObserved && (!recorder || recorder.state === 'inactive')) {
      deactivateOverlay();
      return;
    }

    monitorFrame = requestAnimationFrame(monitorRecording);
  }

  function activateOverlay() {
    if (active) return;
    active = true;
    recordingObserved = false;
    document.body.classList.add('narration-recording-active');
    overlay.classList.add('active');
    const mode = document.querySelector('#narrationRecordingMode');
    if (mode) mode.textContent = 'マイク準備中';
    stateText.textContent = 'マイクの準備ができると、映像と録音が同時に始まります';
    prepareVisual();
    monitorFrame = requestAnimationFrame(monitorRecording);
  }

  function deactivateOverlay() {
    if (!active) return;
    active = false;
    cancelAnimationFrame(monitorFrame);
    monitorFrame = 0;

    const visual = currentVisual();
    if (visual instanceof HTMLVideoElement) {
      visual.pause();
      visual.muted = visualWasMuted;
      visual.controls = visualHadControls;
    }

    restoreAtMarker(visualBox, visualMarker);
    restoreAtMarker(clock, clockMarker);
    restoreAtMarker(stopButton, stopMarker);
    overlay.classList.remove('active');
    document.body.classList.remove('narration-recording-active');
  }

  startButton.onclick = async function startNarrationWithVisibleVideo(event) {
    if (recorder || startButton.disabled) return;
    activateOverlay();
    await originalStart?.call(this, event);

    // The original handler reports permission/MediaRecorder failures itself.
    // Close the overlay when recording did not actually begin.
    if (!recorder || recorder.state !== 'recording') {
      deactivateOverlay();
    }
  };

  stopButton.onclick = function stopNarrationAndRestoreEditor(event) {
    freezeVisualAtEnd();
    const result = originalStop?.call(this, event);
    deactivateOverlay();
    return result;
  };

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden || !active) return;
    if (recorder && recorder.state !== 'inactive') {
      stopButton.click();
      recordStatus.textContent = '画面を離れたため、後入れ音声の録音を停止しました。';
    } else {
      deactivateOverlay();
    }
  }, {capture: true});

  window.addEventListener('pagehide', () => {
    if (active && recorder && recorder.state !== 'inactive') {
      try { recorder.stop(); } catch {}
    }
    deactivateOverlay();
  }, {capture: true});
})();
