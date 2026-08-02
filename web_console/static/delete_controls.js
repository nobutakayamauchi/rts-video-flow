(() => {
  'use strict';

  const DELETE_CLASS = 'rts-inline-delete';
  let deleting = false;

  function normalizeApiUrl(input) {
    try {
      const url = new URL(String(input), location.href);
      if (url.origin !== location.origin) return input;
      url.pathname = url.pathname
        .replace(/^\/vlog\/static\/api\//, '/api/')
        .replace(/^\/static\/api\//, '/api/');
      return url.toString();
    } catch (_) {
      return input;
    }
  }

  function installApiCompatibilityShim() {
    if (window.__rtsApiShimInstalled) return;
    window.__rtsApiShimInstalled = true;

    const originalFetch = window.fetch.bind(window);
    window.fetch = (input, init) => {
      if (input instanceof Request) {
        const fixed = normalizeApiUrl(input.url);
        if (fixed !== input.url) input = new Request(fixed, input);
      } else {
        input = normalizeApiUrl(input);
      }
      return originalFetch(input, init);
    };

    const originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
      return originalOpen.call(this, method, normalizeApiUrl(url), ...rest);
    };
  }

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
    const selectors = document.querySelector('#compilePanel:not(.hidden)')
      ? ['#compileStatus', '#status', '#loadStatus']
      : ['#materialStatus', '#status', '#loadStatus'];
    for (const selector of selectors) {
      const element = document.querySelector(selector);
      if (!element) continue;
      if (typeof status === 'function' && selector !== '#status' && selector !== '#loadStatus') {
        status(selector, message);
      } else if (typeof setStatus === 'function' && (selector === '#status' || selector === '#loadStatus')) {
        setStatus(selector, message);
      } else {
        element.textContent = message;
      }
      return;
    }
  }

  function mediaKind(file) {
    const type = String(file?.type || '').toLowerCase();
    const name = String(file?.name || '').toLowerCase();
    if (type.startsWith('image/') || /\.(jpe?g|png|webp)$/.test(name)) return 'image';
    if (type.startsWith('video/') || /\.(mp4|mov|m4v|webm)$/.test(name)) return 'video';
    return 'unknown';
  }

  function expectedKind(role) {
    return role === 'screenshot' ? 'image' : 'video';
  }

  function configureFileInput() {
    const input = document.querySelector('#fileInput');
    const role = document.querySelector('#role');
    if (!input || !role) return;
    const expected = expectedKind(role.value);
    input.accept = expected === 'image' ? 'image/*' : 'video/*';
  }

  function rejectWrongFile(event) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    const role = document.querySelector('#role')?.value;
    if (!file || !role) return;
    const expected = expectedKind(role);
    const actual = mediaKind(file);
    if (actual === expected) return;

    event.preventDefault();
    event.stopImmediatePropagation();
    input.value = '';
    if (typeof state !== 'undefined') {
      state.blob = null;
      state.blobName = '';
    }
    const save = document.querySelector('#saveMaterial');
    if (save) save.disabled = true;
    const label = expected === 'image' ? '画像' : '動画';
    setPanelStatus(`この素材種別には${label}ファイルだけを選べます。選択を取り消しました。`);
  }

  function installRoleGuards() {
    const input = document.querySelector('#fileInput');
    const role = document.querySelector('#role');
    if (input && !input.dataset.rtsRoleGuard) {
      input.dataset.rtsRoleGuard = '1';
      input.addEventListener('change', rejectWrongFile, true);
    }
    if (role && !role.dataset.rtsRoleGuard) {
      role.dataset.rtsRoleGuard = '1';
      role.addEventListener('change', () => setTimeout(configureFileInput, 0));
    }
    configureFileInput();
  }

  async function deleteSavedItem(itemId) {
    if (deleting || typeof state === 'undefined') return;
    const index = state.timeline.findIndex(item => String(item.id) === String(itemId));
    const item = state.timeline[index];
    if (!item) return;

    const title = itemTitle(item, index);
    if (!confirm(`${title}を削除しますか？\n\n素材ファイルは完全消去せず、.trashへ退避します。`)) return;

    deleting = true;
    document.querySelectorAll(`.${DELETE_CLASS}`).forEach(button => button.disabled = true);
    setPanelStatus('素材を削除中…');

    const body = new FormData();
    body.append('project', state.project);
    body.append('action', 'delete');
    body.append('item_id', itemId);

    try {
      const response = await fetch(new URL('/api/material', location.origin), {
        method: 'POST',
        body,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);

      state.timeline = data.timeline || [];
      if (typeof renderTimeline === 'function') {
        if (document.querySelector('#timeline')) renderTimeline('#timeline');
        if (document.querySelector('#finalTimeline')) renderTimeline('#finalTimeline');
      } else if (typeof load === 'function') {
        await load();
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
    const message = '選択・録画を破棄しました。別の素材を選び直せます。';
    const target = document.querySelector('#materialStatus');
    if (target) target.textContent = message;
  }

  function discardNarration() {
    if (typeof state === 'undefined') return;
    try {
      const recorder = state.audioRecorder || state.recorder;
      if (recorder && recorder.state !== 'inactive') {
        recorder.onstop = () => {};
        recorder.stop();
      }
    } catch (_) {}
    try {
      const stream = state.audioStream || state.stream;
      if (stream) stream.getTracks().forEach(track => track.stop());
    } catch (_) {}

    if ('audioBlob' in state) state.audioBlob = null;
    if ('audioChunks' in state) state.audioChunks = [];
    if (document.querySelector('#record') && 'blob' in state) state.blob = null;
    if (document.querySelector('#record') && 'chunks' in state) state.chunks = [];

    const preview = document.querySelector('#audioPreview') || document.querySelector('#editor #preview');
    if (preview) {
      preview.pause();
      preview.removeAttribute('src');
      preview.classList.add('hidden');
    }
    const save = document.querySelector('#saveNarration') || document.querySelector('#editor #save');
    if (save) save.disabled = true;
    setPanelStatus('録音を破棄しました。録り直せます。');
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

    const saveNarration = document.querySelector('#saveNarration') || document.querySelector('#editor #save');
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
    installRoleGuards();
    enhanceTimeline('#timeline');
    enhanceTimeline('#finalTimeline');
  }

  installApiCompatibilityShim();
  const observer = new MutationObserver(() => enhanceAll());
  observer.observe(document.documentElement, { childList: true, subtree: true });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', enhanceAll, { once: true });
  } else {
    enhanceAll();
  }
})();
