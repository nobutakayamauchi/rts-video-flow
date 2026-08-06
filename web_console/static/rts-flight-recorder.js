(() => {
  'use strict';

  if (window.RTSFlightRecorder) return;

  const MAX_QUEUE = 500;
  const BATCH_SIZE = 50;
  const FLUSH_MS = 5000;
  const INGEST_PATH = '/api/flight-recorder/events';
  const REDACTED = '[REDACTED]';
  const SENSITIVE_KEY = /(authorization|cookie|token|secret|password|passwd|api[-_]?key|session)/i;
  const SESSION_KEY = 'rts-flight-recorder-session-id';
  const SEQUENCE_KEY = 'rts-flight-recorder-sequence';
  const queue = [];
  let enabled = true;
  let flushing = false;
  let flushTimer = 0;
  let sessionId = sessionStorage.getItem(SESSION_KEY) || (crypto.randomUUID ? crypto.randomUUID() : `rts-fr-${Date.now()}-${Math.random().toString(16).slice(2)}`);
  let sequence = Number(sessionStorage.getItem(SEQUENCE_KEY) || 0);
  sessionStorage.setItem(SESSION_KEY, sessionId);

  function sanitize(value, depth = 0) {
    if (depth > 6) return '[TRUNCATED]';
    if (Array.isArray(value)) return value.slice(0, 50).map(item => sanitize(item, depth + 1));
    if (!value || typeof value !== 'object') return value;
    const out = {};
    for (const [key, item] of Object.entries(value)) {
      out[key] = SENSITIVE_KEY.test(key) ? REDACTED : sanitize(item, depth + 1);
    }
    return out;
  }

  function targetSummary(target) {
    if (!(target instanceof Element)) return {};
    return {
      tag: target.tagName.toLowerCase(),
      id: target.id || null,
      role: target.getAttribute('role'),
      name: target.getAttribute('name'),
      action: target.dataset?.action || null,
      text: (target.getAttribute('aria-label') || target.textContent || '').trim().slice(0, 120),
    };
  }

  function scheduleFlush(delay = FLUSH_MS) {
    if (flushTimer) window.clearTimeout(flushTimer);
    flushTimer = window.setTimeout(() => flush().catch(() => {}), delay);
  }

  function record(type, payload = {}) {
    if (!enabled) return null;
    sequence += 1;
    sessionStorage.setItem(SEQUENCE_KEY, String(sequence));
    const event = {
      version: 1,
      session_id: sessionId,
      event_id: crypto.randomUUID ? crypto.randomUUID() : `${sessionId}-${sequence}`,
      sequence,
      recorded_at: new Date().toISOString(),
      type,
      page: {
        path: location.pathname,
        query_keys: [...new URLSearchParams(location.search).keys()],
        visibility: document.visibilityState,
        online: navigator.onLine,
      },
      payload: sanitize(payload),
    };
    queue.push(event);
    if (queue.length > MAX_QUEUE) queue.shift();
    window.dispatchEvent(new CustomEvent('rts-flight-recorder:event', {detail: event}));
    if (queue.length >= BATCH_SIZE) scheduleFlush(0);
    else scheduleFlush();
    return event;
  }

  const originalFetch = window.fetch.bind(window);

  async function flush() {
    if (flushing || !queue.length || !navigator.onLine) {
      scheduleFlush();
      return {accepted: 0, pending: queue.length};
    }
    flushing = true;
    const batch = queue.slice(0, BATCH_SIZE);
    try {
      const response = await originalFetch(INGEST_PATH, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({session_id: sessionId, events: batch}),
        keepalive: true,
        cache: 'no-store',
      });
      if (!response.ok) throw new Error(`flight recorder ingest HTTP ${response.status}`);
      queue.splice(0, batch.length);
      const result = await response.json().catch(() => ({}));
      if (queue.length) scheduleFlush(0);
      else scheduleFlush();
      return {...result, pending: queue.length};
    } catch (error) {
      scheduleFlush(Math.min(30000, FLUSH_MS * 2));
      window.dispatchEvent(new CustomEvent('rts-flight-recorder:flush-error', {detail: {message: String(error?.message || error)}}));
      return {accepted: 0, pending: queue.length, error: String(error?.message || error)};
    } finally {
      flushing = false;
    }
  }

  function beaconFlush() {
    if (!queue.length || !navigator.sendBeacon) return false;
    const batch = queue.slice(0, BATCH_SIZE);
    const blob = new Blob([JSON.stringify({session_id: sessionId, events: batch})], {type: 'application/json'});
    const sent = navigator.sendBeacon(INGEST_PATH, blob);
    if (sent) queue.splice(0, batch.length);
    return sent;
  }

  function installInteractionHooks() {
    document.addEventListener('pointerup', event => {
      const target = event.target instanceof Element ? event.target.closest('button,a,input,select,textarea,[role="button"],[data-action]') : null;
      if (target) record('interaction', {kind: 'pointerup', target: targetSummary(target)});
    }, true);
    document.addEventListener('submit', event => {
      record('interaction', {kind: 'submit', target: targetSummary(event.target)});
    }, true);
  }

  function installNavigationHooks() {
    const wrap = method => {
      const original = history[method];
      history[method] = function(...args) {
        const before = location.href;
        const result = original.apply(this, args);
        record('navigation', {kind: method, before_path: new URL(before).pathname, after_path: location.pathname});
        return result;
      };
    };
    wrap('pushState');
    wrap('replaceState');
    window.addEventListener('popstate', () => record('navigation', {kind: 'popstate', after_path: location.pathname}));
    document.addEventListener('visibilitychange', () => record('visibility', {state: document.visibilityState}));
  }

  function installErrorHooks() {
    window.addEventListener('error', event => record('js_error', {
      message: String(event.message || 'unknown error').slice(0, 1000),
      filename: event.filename ? new URL(event.filename, location.href).pathname : null,
      line: event.lineno || null,
      column: event.colno || null,
    }));
    window.addEventListener('unhandledrejection', event => record('promise_rejection', {
      message: String(event.reason?.message || event.reason || 'unhandled rejection').slice(0, 1000),
    }));
    window.addEventListener('online', () => { record('network', {state: 'online'}); scheduleFlush(0); });
    window.addEventListener('offline', () => record('network', {state: 'offline'}));
  }

  function installFetchHook() {
    window.fetch = async function(input, init = {}) {
      const started = performance.now();
      const url = new URL(typeof input === 'string' ? input : input.url, location.href);
      const method = String(init.method || (typeof input !== 'string' && input.method) || 'GET').toUpperCase();
      if (url.pathname === INGEST_PATH) return originalFetch(input, init);
      try {
        const response = await originalFetch(input, init);
        record('api_result', {
          method,
          path: url.pathname,
          status: response.status,
          ok: response.ok,
          duration_ms: Math.round(performance.now() - started),
        });
        return response;
      } catch (error) {
        record('api_error', {
          method,
          path: url.pathname,
          message: String(error?.message || error).slice(0, 1000),
          duration_ms: Math.round(performance.now() - started),
        });
        throw error;
      }
    };
  }

  function exportSession() {
    return {
      version: 1,
      session_id: sessionId,
      exported_at: new Date().toISOString(),
      event_count: queue.length,
      events: queue.slice(),
    };
  }

  window.RTSFlightRecorder = {
    record,
    flush,
    exportSession,
    clear() { queue.length = 0; },
    stop() {
      if (!enabled) return;
      record('session', {state: 'stopped'});
      enabled = false;
      flush().catch(() => {});
    },
    start(newSessionId) {
      sessionId = newSessionId || (crypto.randomUUID ? crypto.randomUUID() : `rts-fr-${Date.now()}`);
      queue.length = 0;
      sequence = 0;
      enabled = true;
      sessionStorage.setItem(SESSION_KEY, sessionId);
      sessionStorage.setItem(SEQUENCE_KEY, '0');
      record('session', {state: 'started'});
      return sessionId;
    },
    get sessionId() { return sessionId; },
    get size() { return queue.length; },
  };

  installInteractionHooks();
  installNavigationHooks();
  installErrorHooks();
  installFetchHook();
  window.addEventListener('pagehide', beaconFlush);
  record('session', {state: 'started', user_agent_family: navigator.userAgent.includes('Safari') ? 'safari' : 'other'});
})();
