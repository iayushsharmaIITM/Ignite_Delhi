/* Shared Clerk bootstrap. Every page loads this so the sidebar user area and
 * that page's API calls share ONE session.
 *
 *   KestrelAuth.mode()         'off' | 'clerk'
 *   KestrelAuth.signedIn()     boolean (clerk mode)
 *   KestrelAuth.authHeaders()  { Authorization: Bearer <jwt> } — {}
 *                              when auth is off or the token is unavailable
 *   KestrelAuth.signOut()      end the session, fire listeners
 *   KestrelAuth.openAccount()  Clerk's account-management modal
 *   KestrelAuth.addListener(fn)

 * ClerkJS v5's browser build reads the publishable key from the
 * data-clerk-publishable-key attribute at script-eval time; the instance
 * itself is booted by Clerk.load(), which fetches the environment, runs the
 * dev-browser handshake and wires the UI renderer. Every mount* / open*
 * call throws "components are not ready yet" until load() has resolved.
 */
(function () {
  const listeners = [];
  let mode = 'off';
  let booted = null;   // promise, so parallel callers await one boot

  function emit() { listeners.forEach(fn => { try { fn(state()); } catch (e) {} }); }

  function state() {
    return { mode, signedIn: !!(mode === 'clerk' && window.Clerk && window.Clerk.user) };
  }

  function loadScript(publishableKey) {
    return new Promise((resolve, reject) => {
      if (window.Clerk) { resolve(); return; }
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/@clerk/clerk-js@5/dist/clerk.browser.js';
      s.setAttribute('data-clerk-publishable-key', publishableKey);
      s.onload = resolve; s.onerror = () => reject(new Error('Clerk.js failed to load'));
      document.head.appendChild(s);
    });
  }

  async function init() {
    if (booted) return booted;
    booted = (async () => {
      let cfg;
      try { cfg = await (await fetch('/api/config')).json(); } catch (e) { return; }
      if (cfg.authMode !== 'clerk' || !cfg.publishableKey) { emit(); return; }
      mode = 'clerk';
      try {
        await loadScript(cfg.publishableKey);
        await window.Clerk.load({ publishableKey: cfg.publishableKey });
        window.Clerk.addListener(emit);
      } catch (e) {
        console.warn('auth init failed:', e.message);
      }
      emit();
    })();
    return booted;
  }

  async function authHeaders() {
    if (mode !== 'clerk') return {};
    try {
      const tok = await window.Clerk?.session?.getToken?.();
      if (tok) return { Authorization: 'Bearer ' + tok };
    } catch (e) { /* refresh failed — the call proceeds and 401s */ }
    return {};
  }

  async function signOut() {
    try { await window.Clerk?.signOut?.(); } catch (e) { /* session may be gone */ }
    emit();
  }

  function openAccount() { try { window.Clerk?.openUserProfile?.(); } catch (e) {} }

  window.KestrelAuth = {
    init, authHeaders, signOut, openAccount, state,
    addListener(fn) { listeners.push(fn); fn(state()); },
    get mode() { return mode; },
    get user() { return window.Clerk?.user || null; },
    isReady: () => !!(mode === 'off' || (window.Clerk && window.Clerk.loaded)),
  };
  init();
})();
