(() => {
  'use strict';

  if (window.RTSFlightRecorder) return;

  const MAX_QUEUE = 500;
  const REDACTED = '[REDACTED]';
  const SENSITIVE_KEY = /(authorization|cookie|token|secret|password|passwd|api[-_]?key|session)/i;
  const queue = [];
  let sequence = 0;
  let enabled = true;
  let sessionId = crypto.randomUUID ? crypto.randomUUID() : `rts-fr-${Date.now()}-${Math.random().toString(16).slice(2)}`;

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

  function record(type, payload = {}) {
    if (!enabled) return null;
    const event = {
      version: 1,
      session_id: sessionId,
      event_id: crypto.randomUUID ? crypto.randomUUID() : `${sessionId}-${sequence + 1}`,
      sequence: ++sequence,
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
    return event;
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
    window.addEventListener('online', () => record('network', {state: 'online'}));
    window.addEventListener('offline', () => record('network', {state: 'offline'}));
  }

  function installFetchHook() {
    const originalFetch = window.fetch.bind(window);
    window.fetch = async function(input, init = {}) {
      const started = performance.now();
      const url = new URL(typeof input === 'string' ? input : input.url, location.href);
      const method = String(init.method || (typeof input !== 'string' && input.method) || 'GET').toUpperCase();
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
    exportSession,
    clear() { queue.length = 0; sequence = 0; },
    stop() { enabled = false; record('session', {state: 'stopped'}); },
    start(newSessionId) {
      sessionId = newSessionId || (crypto.randomUUID ? crypto.randomUUID() : `rts-fr-${Date.now()}`);
      queue.length = 0;
      sequence = 0;
      enabled = true;
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
  record('session', {state: 'started', user_agent_family: navigator.userAgent.includes('Safari') ? 'safari' : 'other'});
})();
