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
    if (mode !== 'clerk' || !window.Clerk) return { mode, signedIn: false };
    // A client holding sessions IS signed in. After the Account Portal
    // redirects back, clerk-js reloads the client and the `user` ref is
    // transiently null — treating that as signed-out re-opened the gate and
    // mounted <SignIn>, which Clerk answered by redirecting to afterSignIn:
    // an endless reload loop. Sessions are the durable truth.
    const sessions = (window.Clerk.client && window.Clerk.client.sessions) || [];
    return { mode, signedIn: !!window.Clerk.user || sessions.length > 0 };
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
    // Wait for boot: parse-time callers (history restore, graph fetch) run
    // before /api/config + Clerk.load() resolve, and mode is still 'off'
    // until then — without this await they get {} and fire unauthenticated.
    try { await booted; } catch (e) { /* boot failed; fall through to {} */ }
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

  // Theme-matched Clerk component variables — shared by the gate's mounted
  // sign-in and the account modal, so Clerk surfaces follow the app theme.
  function appearance() {
    const light = document.documentElement.dataset.theme === 'light';
    return { variables: light ? {
        colorBackground: '#ffffff', colorText: '#201d18', colorForeground: '#201d18',
        colorInputBackground: '#f3f1ec', colorInputText: '#201d18',
        colorPrimary: '#b45309', colorPrimaryForeground: '#ffffff',
        colorMutedForeground: '#6f6a60', colorBorder: 'rgba(28,24,16,.15)',
      } : {
        colorBackground: '#232323', colorText: '#e9e9e9', colorForeground: '#e9e9e9',
        colorInputBackground: '#2b2b2b', colorInputText: '#e9e9e9',
        colorPrimary: '#e8863b', colorPrimaryForeground: '#161616',
        colorMutedForeground: '#9b9b9b', colorBorder: 'rgba(255,255,255,.13)',
      } };
  }

  function openAccount() {
    try { window.Clerk?.openUserProfile?.({ appearance: appearance() }); } catch (e) {}
  }

  window.KestrelAuth = {
    init, authHeaders, signOut, openAccount, appearance, state,
    addListener(fn) { listeners.push(fn); fn(state()); },
    get mode() { return mode; },
    get user() { return window.Clerk?.user || null; },
    isReady: () => !!(mode === 'off' || (window.Clerk && window.Clerk.loaded)),
  };
  init();
})();
