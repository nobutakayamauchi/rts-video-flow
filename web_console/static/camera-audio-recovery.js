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
  style.dataset.cameraControlLayout = 'v2';
  style.textContent = `
    body.camera-active {
      overflow: hidden;
    }
    body.camera-active #cameraSafety {
      display: none !important;
    }
    #cameraPreviewFrame {
      display: none;
    }
    #cameraPreviewFrame.active {
      position: fixed;
      inset:
        max(8px, env(safe-area-inset-top))
        max(8px, env(safe-area-inset-right))
        max(8px, env(safe-area-inset-bottom))
        max(8px, env(safe-area-inset-left));
      z-index: 1000;
      display: block;
      overflow: hidden;
      border: 3px solid #ff3b30;
      border-radius: 20px;
      background: #000;
      box-shadow: 0 18px 60px rgba(0, 0, 0, 0.72);
    }
    #cameraPreviewFrame #preview {
      display: block;
      width: 100%;
      height: 100%;
      max-height: none;
      margin: 0;
      border-radius: 0;
      object-fit: contain;
      background: #000;
    }
    .camera-frame-overlay {
      position: absolute;
      left: 0;
      right: 0;
      z-index: 3;
      color: #fff;
      background: rgba(12, 15, 20, 0.68);
      -webkit-backdrop-filter: blur(12px);
      backdrop-filter: blur(12px);
    }
    #cameraTopOverlay {
      top: 0;
      padding: 12px 14px 11px;
      border-bottom: 1px solid rgba(255,255,255,.2);
      pointer-events: none;
    }
    #cameraTopOverlay .camera-overlay-head {
      display: grid;
      grid-template-columns: auto 1fr auto;
      align-items: center;
      gap: 10px;
    }
    #cameraTopOverlay .camera-safety-title,
    #cameraTopOverlay .camera-elapsed {
      color: #fff;
    }
    #cameraTopOverlay .camera-note {
      margin: 7px 0 0;
      color: #ffe1de;
      font-size: .9rem;
      line-height: 1.4;
    }
    #cameraTopOverlay .camera-disappears-note {
      margin: 5px 0 0;
      color: #fff4b8;
      font-size: .83rem;
      font-weight: 850;
    }
    #cameraBottomOverlay {
      bottom: 0;
      padding: 10px 12px calc(10px + env(safe-area-inset-bottom));
      border-top: 1px solid rgba(255,255,255,.2);
    }
    #cameraBottomOverlay .camera-dock-label {
      margin: 0 0 8px;
      text-align: center;
      color: #fff4b8;
      font-size: .88rem;
      font-weight: 900;
    }
    #cameraBottomOverlay .camera-record-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    #cameraBottomOverlay button {
      min-height: 54px;
      margin-top: 0;
      touch-action: manipulation;
    }
    #cameraBottomOverlay #endCamera {
      min-height: 46px;
      margin-top: 8px;
    }
    @media (max-width: 430px) {
      #cameraPreviewFrame.active {
        border-radius: 16px;
      }
      #cameraTopOverlay {
        padding: 10px 11px 9px;
      }
      #cameraTopOverlay .camera-note {
        font-size: .82rem;
      }
      #cameraBottomOverlay {
        padding-left: 9px;
        padding-right: 9px;
      }
    }
  `;
  document.head.appendChild(style);

  const preview = document.querySelector('#preview');
  const startButton = document.querySelector('#startRecord');
  const stopButton = document.querySelector('#stopRecord');
  const endButton = document.querySelector('#endCamera');
  const safetyBox = document.querySelector('#cameraSafety');
  const safetyDot = safetyBox?.querySelector('.camera-dot');
  const safetyTitle = document.querySelector('#cameraSafetyTitle');
  const safetyElapsed = document.querySelector('#cameraElapsed');
  const safetyDetail = document.querySelector('#cameraSafetyDetail');
  if (!preview || !startButton || !stopButton || !endButton) return;

  const previewHome = preview.parentElement;
  const previewMarker = document.createComment('camera-preview-home');
  previewHome?.insertBefore(previewMarker, preview);

  const originalRecordRow = startButton.parentElement;
  const originalEndParent = endButton.parentElement;

  const frame = document.createElement('div');
  frame.id = 'cameraPreviewFrame';
  frame.setAttribute('role', 'region');
  frame.setAttribute('aria-label', 'カメラプレビューと撮影操作');

  const topOverlay = document.createElement('div');
  topOverlay.id = 'cameraTopOverlay';
  topOverlay.className = 'camera-frame-overlay';

  const overlayHead = document.createElement('div');
  overlayHead.className = 'camera-overlay-head';
  if (safetyDot) overlayHead.appendChild(safetyDot);
  if (safetyTitle) overlayHead.appendChild(safetyTitle);
  if (safetyElapsed) overlayHead.appendChild(safetyElapsed);
  topOverlay.appendChild(overlayHead);
  if (safetyDetail) topOverlay.appendChild(safetyDetail);

  const disappearsNote = document.createElement('p');
  disappearsNote.className = 'camera-disappears-note';
  disappearsNote.textContent = 'この表示はカメラ・撮影の終了後に消えます';
  topOverlay.appendChild(disappearsNote);

  const bottomOverlay = document.createElement('div');
  bottomOverlay.id = 'cameraBottomOverlay';
  bottomOverlay.className = 'camera-frame-overlay';

  const label = document.createElement('p');
  label.className = 'camera-dock-label';
  label.textContent = '撮影操作 — ボタンは映像の上に固定されています';

  const recordRow = document.createElement('div');
  recordRow.className = 'camera-record-row';
  recordRow.append(startButton, stopButton);
  bottomOverlay.append(label, recordRow, endButton);

  frame.append(preview, topOverlay, bottomOverlay);
  document.body.appendChild(frame);

  function restorePreviewHome() {
    if (!previewMarker.parentNode) return;
    previewMarker.parentNode.insertBefore(preview, previewMarker.nextSibling);
  }

  function setCameraLayoutActive(active) {
    document.body.classList.toggle('camera-active', active);
    frame.classList.toggle('active', active);
    if (active) {
      frame.insertBefore(preview, topOverlay);
    } else {
      restorePreviewHome();
    }
  }

  const originalUpdateCameraSafety = updateCameraSafety;
  updateCameraSafety = function updateSafetyAndOverlays(recording = false) {
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

  // Moving the existing elements preserves all original handlers and the
  // existing elapsed-time updates while replacing the bulky page block with
  // semi-transparent overlays on the camera frame.
  originalRecordRow?.classList?.add('camera-controls-placeholder');
  originalEndParent?.classList?.add('camera-end-placeholder');
})();
