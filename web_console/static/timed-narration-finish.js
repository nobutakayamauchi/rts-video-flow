(() => {
  const playButton = document.querySelector('#playTogether');
  const discardButton = document.querySelector('#discard');
  const startButton = document.querySelector('#start');
  const stopButton = document.querySelector('#stop');
  const audioFileInput = document.querySelector('#audioFile');
  const imageDurationInput = document.querySelector('#imageDuration');
  const fitImageButton = document.querySelector('#fitImage');
  const keepImageButton = document.querySelector('#keepImage');
  const saveButton = document.querySelector('#save');
  const skipLink = document.querySelector('#skip');
  const backLink = document.querySelector('#back');
  const hintInput = document.querySelector('#hint');
  const recordStatus = document.querySelector('#recordStatus');
  const saveStatus = document.querySelector('#saveStatus');
  const savePanel = saveButton?.closest('.panel');

  if (!playButton || !saveButton || !skipLink || !recordStatus || !saveStatus) return;

  const style = document.createElement('style');
  style.dataset.timedNarrationFinish = 'v1';
  style.textContent = `
    #playTogether.previewing {
      background: #ffd479 !important;
      color: #17120a !important;
    }
    .narration-save-panel.saved {
      border-color: #66d19e;
      box-shadow: 0 0 0 3px rgba(102, 209, 158, .12);
    }
    #save.saved-button {
      background: #285d48 !important;
      color: #eafff4 !important;
      opacity: 1;
    }
    #skip.saved-return {
      background: #ffc84a !important;
      color: #17120a !important;
      border: 0 !important;
      font-size: 1.08rem;
      min-height: 54px;
    }
    .save-success-heading {
      margin: 12px 0 4px;
      color: #66d19e;
      font-weight: 950;
      font-size: 1.15rem;
    }
    .saving-lock {
      pointer-events: none;
      opacity: .7;
    }
  `;
  document.head.appendChild(style);
  savePanel?.classList.add('narration-save-panel');

  let previewFrame = 0;
  let previewActive = false;
  let previewStartedAt = 0;
  let previousVisualMuted = false;
  let saveInFlight = false;
  let saved = false;

  function previewResultText(target) {
    const delta = Number(selectedDuration || 0) - target;
    if (delta > 0.05) {
      return `完成形プレビューを終了しました（${target.toFixed(1)}秒）。超過した${delta.toFixed(1)}秒は再生していません。`;
    }
    if (delta < -0.05) {
      return `完成形プレビューを終了しました（${target.toFixed(1)}秒）。最後の${(-delta).toFixed(1)}秒は無音として確認しました。`;
    }
    return `完成形プレビューを終了しました（${target.toFixed(1)}秒）。`;
  }

  function stopTogetherPreview({reset = true, message = ''} = {}) {
    cancelAnimationFrame(previewFrame);
    previewFrame = 0;

    const audio = document.querySelector('#audioPreview');
    audio?.pause();
    if (reset && audio) {
      try { audio.currentTime = 0; } catch {}
    }

    if (info?.type === 'video' && visualElement) {
      visualElement.pause();
      if (reset) {
        try { visualElement.currentTime = 0; } catch {}
      }
      visualElement.muted = previousVisualMuted;
    }

    previewActive = false;
    playButton.classList.remove('previewing');
    playButton.textContent = '映像と合わせて確認';
    if (!saved) playButton.disabled = !selectedFile;
    if (message) recordStatus.textContent = message;
  }

  function finishTogetherPreview() {
    const target = currentTarget();
    stopTogetherPreview({message: previewResultText(target)});
  }

  function previewTick() {
    if (!previewActive) return;
    const elapsed = (performance.now() - previewStartedAt) / 1000;
    if (elapsed >= currentTarget()) {
      finishTogetherPreview();
      return;
    }
    previewFrame = requestAnimationFrame(previewTick);
  }

  playButton.onclick = async () => {
    if (saved || !selectedUrl) return;
    if (previewActive) {
      stopTogetherPreview({message: '完成形プレビューを停止しました。'});
      return;
    }

    stopTogetherPreview();
    const audio = document.querySelector('#audioPreview');
    if (!audio) return;
    audio.pause();
    audio.currentTime = 0;

    const target = currentTarget();
    previewActive = true;
    playButton.disabled = false;
    playButton.classList.add('previewing');
    playButton.textContent = '■ 確認を停止';
    recordStatus.textContent = `完成形プレビュー中… ${target.toFixed(1)}秒で映像と音声を止めます。`;

    try {
      const plays = [audio.play()];
      if (info?.type === 'video' && visualElement) {
        visualElement.pause();
        visualElement.currentTime = 0;
        previousVisualMuted = visualElement.muted;
        visualElement.muted = true;
        plays.unshift(visualElement.play());
      }
      await Promise.all(plays);
      previewStartedAt = performance.now();
      previewFrame = requestAnimationFrame(previewTick);
    } catch (error) {
      stopTogetherPreview({message: `同時再生できませんでした: ${error.message}`});
    }
  };

  function wrapStopPreview(element, eventName = 'onclick') {
    if (!element) return;
    const original = element[eventName];
    element[eventName] = function wrappedHandler(...args) {
      if (previewActive) stopTogetherPreview();
      return original?.apply(this, args);
    };
  }

  wrapStopPreview(discardButton);
  wrapStopPreview(startButton);
  wrapStopPreview(stopButton);
  wrapStopPreview(fitImageButton);
  wrapStopPreview(keepImageButton);

  if (audioFileInput) {
    const originalAudioChange = audioFileInput.onchange;
    audioFileInput.onchange = function wrappedAudioChange(...args) {
      if (previewActive) stopTogetherPreview();
      return originalAudioChange?.apply(this, args);
    };
  }
  if (imageDurationInput) {
    const originalDurationInput = imageDurationInput.oninput;
    imageDurationInput.oninput = function wrappedDurationInput(...args) {
      if (previewActive) stopTogetherPreview();
      return originalDurationInput?.apply(this, args);
    };
  }

  function lockEditingAfterSave() {
    saved = true;
    stopTogetherPreview();
    savePanel?.classList.add('saved');

    saveButton.disabled = true;
    saveButton.textContent = '✓ 保存済み';
    saveButton.classList.add('saved-button');

    const controls = [
      startButton,
      stopButton,
      audioFileInput,
      imageDurationInput,
      fitImageButton,
      keepImageButton,
      discardButton,
      playButton,
      hintInput,
    ];
    controls.forEach(element => {
      if (element) element.disabled = true;
    });

    skipLink.textContent = '構成へ戻る';
    skipLink.classList.remove('ghost');
    skipLink.classList.add('saved-return');
    skipLink.removeAttribute('aria-disabled');
    skipLink.style.pointerEvents = '';
    backLink.textContent = '構成へ戻る';

    if (!savePanel?.querySelector('.save-success-heading')) {
      const heading = document.createElement('p');
      heading.className = 'save-success-heading';
      heading.textContent = '後入れ音声を保存しました';
      saveStatus.before(heading);
    }
  }

  function setSavingState(active) {
    saveInFlight = active;
    saveButton.disabled = active || !selectedFile;
    saveButton.textContent = active ? '保存処理中…' : '後入れ音声を保存';
    skipLink.classList.toggle('saving-lock', active);
    skipLink.setAttribute('aria-disabled', active ? 'true' : 'false');
  }

  saveButton.onclick = async () => {
    if (saveInFlight || saved || !selectedFile) return;
    stopTogetherPreview();

    const body = new FormData();
    body.append('project', project);
    body.append('item_id', itemId);
    body.append('target_duration_seconds', String(currentTarget()));
    body.append('transcript_hint', hintInput?.value || '');
    body.append('media', selectedFile, selectedFile.name);

    setSavingState(true);
    saveStatus.classList.remove('ok');
    saveStatus.textContent = '音声を保存し、指定尺へ整形しています…';

    try {
      const data = await requestJson('api/timed-narration', {method: 'POST', body});
      const fit = {
        'trim-tail': '超過分を末尾でカット',
        'pad-silence': '不足分を無音で補完',
        exact: '尺が一致',
      }[data.fit] || data.fit;

      lockEditingAfterSave();
      saveStatus.classList.add('ok');
      saveStatus.textContent = [
        '保存しました。',
        '元音声：全区間カット',
        `処理：${fit}`,
        `使用尺：${Number(data.targetDurationSeconds).toFixed(1)}秒`,
        '',
        '二重送信を防ぐため、この画面の編集をロックしました。',
        '修正する場合は、構成画面からこの素材を開き直してください。',
      ].join('\n');
    } catch (error) {
      setSavingState(false);
      saveStatus.textContent = `保存失敗: ${error.message}`;
    }
  };

  window.addEventListener('pagehide', () => stopTogetherPreview({reset: false}));
})();
