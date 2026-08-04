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
