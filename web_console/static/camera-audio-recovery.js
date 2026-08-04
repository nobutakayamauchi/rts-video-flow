(() => {
  const patterns = {
    cameraOpen: [[660, 0.12], [0, 0.08], [880, 0.12]],
    recordStart: [[880, 0.11], [660, 0.11]],
    recordStop: [[660, 0.11], [880, 0.11]],
    cameraClose: [[520, 0.12], [390, 0.15]],
  };

  function discardPrivacyAudioContext() {
    const current = state.audioContext;
    state.audioContext = null;
    if (!current || current.state === 'closed') return;
    try {
      const closing = current.close();
      closing?.catch?.(() => {});
    } catch {}
  }

  async function createFreshPrivacyAudioContext() {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) {
      throw new Error('このブラウザでは必須の撮影合図音を再生できません');
    }

    discardPrivacyAudioContext();
    const context = new AudioContextClass();
    state.audioContext = context;
    await context.resume();
    if (context.state !== 'running') {
      await wait(60);
      await context.resume();
    }
    if (context.state !== 'running') {
      discardPrivacyAudioContext();
      throw new Error('撮影合図音を開始できません');
    }
    return context;
  }

  async function getPrivacyAudioContext(kind) {
    // Camera activation always comes from an explicit user tap. Recreate the
    // context here because iOS Safari can leave a foregrounded context silent
    // after the page has been backgrounded.
    if (kind === 'cameraOpen') return createFreshPrivacyAudioContext();

    let context = state.audioContext;
    if (!context || context.state === 'closed' || context.state === 'interrupted') {
      return createFreshPrivacyAudioContext();
    }
    if (context.state !== 'running') {
      try { await context.suspend(); } catch {}
      await context.resume();
    }
    if (context.state !== 'running') return createFreshPrivacyAudioContext();
    return context;
  }

  playPrivacySignal = async function playRecoveredPrivacySignal(kind) {
    const pattern = patterns[kind];
    if (!pattern) throw new Error('不明な撮影合図音です');

    const context = await getPrivacyAudioContext(kind);
    let cursor = context.currentTime + 0.04;
    for (const [frequency, duration] of pattern) {
      if (!frequency) {
        cursor += duration;
        continue;
      }
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.type = 'sine';
      oscillator.frequency.setValueAtTime(frequency, cursor);
      gain.gain.setValueAtTime(0.0001, cursor);
      gain.gain.exponentialRampToValueAtTime(0.18, cursor + 0.015);
      gain.gain.setValueAtTime(0.18, Math.max(cursor + 0.02, cursor + duration - 0.025));
      gain.gain.exponentialRampToValueAtTime(0.0001, cursor + duration);
      oscillator.connect(gain);
      gain.connect(context.destination);
      oscillator.start(cursor);
      oscillator.stop(cursor + duration + 0.01);
      cursor += duration + 0.045;
    }

    await wait(Math.max(100, (cursor - context.currentTime + 0.04) * 1000));
    if (state.audioContext !== context || context.state !== 'running') {
      throw new Error('撮影合図音の再生処理が中断されました');
    }
  };

  const originalEmergencyStopCamera = emergencyStopCamera;
  emergencyStopCamera = function stopCameraAndDiscardInterruptedAudio(message) {
    discardPrivacyAudioContext();
    return originalEmergencyStopCamera(message);
  };

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) discardPrivacyAudioContext();
  }, {capture: true});
  window.addEventListener('pagehide', discardPrivacyAudioContext, {capture: true});
})();

(() => {
  const style = document.createElement('style');
  style.dataset.cameraControlLayout = 'v1';
  style.textContent = `
    body.camera-active {
      padding-bottom: calc(184px + env(safe-area-inset-bottom));
    }
    body.camera-active #preview {
      display: block;
      width: 100%;
      height: auto;
      max-height: min(38svh, 390px);
      object-fit: contain;
      position: relative;
      z-index: 1;
      margin: 10px 0;
    }
    #cameraControlDock {
      position: fixed;
      left: max(10px, env(safe-area-inset-left));
      right: max(10px, env(safe-area-inset-right));
      bottom: max(8px, env(safe-area-inset-bottom));
      z-index: 1000;
      max-width: 740px;
      margin: 0 auto;
      padding: 10px;
      border: 2px solid #52647b;
      border-radius: 18px;
      background: rgba(11, 15, 20, 0.96);
      box-shadow: 0 -8px 30px rgba(0, 0, 0, 0.45);
      -webkit-backdrop-filter: blur(14px);
      backdrop-filter: blur(14px);
    }
    #cameraControlDock.hidden {
      display: none !important;
    }
    #cameraControlDock .camera-dock-label {
      margin: 0 0 7px;
      text-align: center;
      color: #ffd8d5;
      font-size: 0.9rem;
      font-weight: 900;
    }
    #cameraControlDock .camera-record-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    #cameraControlDock button {
      min-height: 52px;
      margin-top: 0;
      touch-action: manipulation;
    }
    #cameraControlDock #endCamera {
      margin-top: 8px;
      min-height: 46px;
    }
    @media (max-width: 430px) {
      body.camera-active #preview {
        max-height: 36svh;
      }
      #cameraControlDock .camera-record-row {
        grid-template-columns: 1fr 1fr;
      }
    }
  `;
  document.head.appendChild(style);

  const startButton = document.querySelector('#startRecord');
  const stopButton = document.querySelector('#stopRecord');
  const endButton = document.querySelector('#endCamera');
  if (!startButton || !stopButton || !endButton) return;

  const originalRecordRow = startButton.parentElement;
  const originalEndParent = endButton.parentElement;
  const dock = document.createElement('div');
  dock.id = 'cameraControlDock';
  dock.className = 'hidden';
  dock.setAttribute('role', 'region');
  dock.setAttribute('aria-label', 'カメラ操作');

  const label = document.createElement('p');
  label.className = 'camera-dock-label';
  label.textContent = 'カメラ操作は常にここに表示されます';

  const recordRow = document.createElement('div');
  recordRow.className = 'camera-record-row';
  recordRow.append(startButton, stopButton);
  dock.append(label, recordRow, endButton);
  document.body.appendChild(dock);

  function setCameraLayoutActive(active) {
    document.body.classList.toggle('camera-active', active);
    dock.classList.toggle('hidden', !active);
    if (active) {
      requestAnimationFrame(() => {
        const preview = document.querySelector('#preview');
        preview?.scrollIntoView?.({block: 'center', behavior: 'smooth'});
      });
    }
  }

  const originalUpdateCameraSafety = updateCameraSafety;
  updateCameraSafety = function updateSafetyAndControls(recording = false) {
    const result = originalUpdateCameraSafety(recording);
    setCameraLayoutActive(Boolean(state.stream));
    return result;
  };

  const originalStopTracksOnly = stopTracksOnly;
  stopTracksOnly = function stopTracksAndRestoreLayout() {
    const result = originalStopTracksOnly();
    setCameraLayoutActive(false);
    return result;
  };

  // Keep fallbacks for script or browser errors. Moving the buttons preserves
  // their existing onclick handlers, but the old containers remain harmless.
  originalRecordRow?.classList?.add('camera-controls-placeholder');
  originalEndParent?.classList?.add('camera-end-placeholder');
})();
