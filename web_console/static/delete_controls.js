(() => {
  'use strict';

  const DELETE_CLASS = 'rts-inline-delete';
  let deleting = false;

  function addStyles() {
    if (document.getElementById('rts-delete-control-style')) return;
    const style = document.createElement('style');
    style.id = 'rts-delete-control-style';
    style.textContent = `
      .${DELETE_CLASS}{background:#ff6b63!important;color:#1b0b09!important;margin-top:12px!important}
      .rts-discard{background:#ff6b63!important;color:#1b0b09!important;margin-top:10px!important}
      .rts-delete-note{color:#aeb9c5;font-size:.86rem;line-height:1.45;margin:8px 0 0}
    `;
    document.head.appendChild(style);
  }

  function itemTitle(item, index) {
    const label = typeof labels !== 'undefined' ? labels[item?.role] : null;
    return `${index + 1}. ${label || item?.role || '素材'}`;
  }

  function setPanelStatus(message) {
    const compileVisible = document.querySelector('#compilePanel:not(.hidden)');
    const target = compileVisible ? '#compileStatus' : '#materialStatus';
    if (typeof status === 'function' && document.querySelector(target)) status(target, message);
  }

  async function deleteSavedItem(itemId) {
    if (deleting || typeof state === 'undefined') return;
    const index = state.timeline.findIndex(item => item.id === itemId);
    const item = state.timeline[index];
    if (!item) return;

    const title = itemTitle(item, index);
    if (!confirm(`${title}を削除しますか？\n\n素材ファイルは完全消去せず、.trashへ退避します。`)) return;

    deleting = true;
    document.querySelectorAll(`.${DELETE_CLASS}`).forEach(button => button.disabled = true);
    setPanelStatus('素材を削除中…');

    const body = new FormData();
    body.append('project', state.project);
    body.append('item_id', itemId);

    try {
      let data;
      if (typeof requestJson === 'function') {
        data = await requestJson('api/material', { method: 'DELETE', body });
      } else {
        const response = await fetch(typeof apiUrl === 'function' ? apiUrl('api/material') : 'api/material', { method: 'DELETE', body });
        data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      }

      state.timeline = data.timeline || [];
      if (typeof renderTimeline === 'function') {
        if (document.querySelector('#timeline')) renderTimeline('#timeline');
        if (document.querySelector('#finalTimeline')) renderTimeline('#finalTimeline');
      }

      const roles = state.timeline.map(value => value.role);
      if (!roles.includes('opening') || !roles.includes('ending')) {
        const privacy = document.querySelector('#privacy');
        const compile = document.querySelector('#compile');
        if (privacy) privacy.checked = false;
        if (compile) compile.disabled = true;
      }

      setPanelStatus('削除しました。元ファイルは .trash に退避されています。');
      enhanceAll();
    } catch (error) {
      setPanelStatus(`削除失敗: ${error.message}`);
    } finally {
      deleting = false;
      document.querySelectorAll(`.${DELETE_CLASS}`).forEach(button => button.disabled = false);
    }
  }

  function enhanceTimeline(selector) {
    if (typeof state === 'undefined') return;
    const container = document.querySelector(selector);
    if (!container) return;
    const cards = [...container.querySelectorAll('.item')];
    cards.forEach((card, index) => {
      const item = state.timeline[index];
      if (!item || card.querySelector(`.${DELETE_CLASS}`)) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = DELETE_CLASS;
      button.textContent = 'この素材を削除';
      button.dataset.itemId = item.id;
      button.addEventListener('click', () => deleteSavedItem(item.id));
      card.appendChild(button);
    });
  }

  function discardMaterial() {
    if (typeof state === 'undefined') return;
    try {
      if (state.recorder && state.recorder.state !== 'inactive') {
        state.recorder.onstop = () => {};
        state.recorder.stop();
      }
    } catch (_) {}
    try { if (typeof stopStream === 'function') stopStream(); } catch (_) {}
    try { if (typeof resetMaterial === 'function') resetMaterial(); } catch (_) {}
    state.blob = null;
    state.blobName = '';
    const button = document.querySelector('#saveMaterial');
    if (button) button.disabled = true;
    if (typeof status === 'function') status('#materialStatus', '選択・録画を破棄しました。別の素材を選び直せます。');
  }

  function discardNarration() {
    if (typeof state === 'undefined') return;
    try {
      if (state.audioRecorder && state.audioRecorder.state !== 'inactive') {
        state.audioRecorder.onstop = () => {};
        state.audioRecorder.stop();
      }
    } catch (_) {}
    try {
      if (state.audioStream) state.audioStream.getTracks().forEach(track => track.stop());
    } catch (_) {}
    state.audioBlob = null;
    state.audioChunks = [];
    const preview = document.querySelector('#audioPreview');
    if (preview) {
      preview.pause();
      preview.removeAttribute('src');
      preview.classList.add('hidden');
    }
    const save = document.querySelector('#saveNarration');
    if (save) save.disabled = true;
    if (typeof status === 'function') status('#narrationStatus', '録音を破棄しました。録り直せます。');
  }

  function addDiscardControls() {
    const saveMaterial = document.querySelector('#saveMaterial');
    if (saveMaterial && !document.querySelector('#discardMaterial')) {
      const button = document.createElement('button');
      button.id = 'discardMaterial';
      button.type = 'button';
      button.className = 'rts-discard';
      button.textContent = '選択・録画を破棄してやり直す';
      button.addEventListener('click', discardMaterial);
      saveMaterial.insertAdjacentElement('afterend', button);
      const note = document.createElement('p');
      note.className = 'rts-delete-note';
      note.textContent = 'まだ保存していない素材だけを取り消します。';
      button.insertAdjacentElement('afterend', note);
    }

    const saveNarration = document.querySelector('#saveNarration');
    if (saveNarration && !document.querySelector('#discardNarration')) {
      const button = document.createElement('button');
      button.id = 'discardNarration';
      button.type = 'button';
      button.className = 'rts-discard';
      button.textContent = 'この録音を破棄して録り直す';
      button.addEventListener('click', discardNarration);
      saveNarration.insertAdjacentElement('afterend', button);
    }
  }

  function enhanceAll() {
    addStyles();
    addDiscardControls();
    enhanceTimeline('#timeline');
    enhanceTimeline('#finalTimeline');
  }

  const observer = new MutationObserver(() => enhanceAll());
  observer.observe(document.documentElement, { childList: true, subtree: true });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', enhanceAll, { once: true });
  } else {
    enhanceAll();
  }
})();
