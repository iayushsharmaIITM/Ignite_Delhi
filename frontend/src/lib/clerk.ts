// Clerk loader — loads the Clerk JS bundle from CDN and boots it.
// Port of the legacy auth.js init() for the React app.
// Mirrors the exact boot sequence from static/auth.js:
//   1. Load the clerk.browser.js script with data-clerk-publishable-key
//   2. Wait for window.Clerk to appear
//   3. Call Clerk.load({ publishableKey }) — this fetches the environment,
//      runs the dev-browser handshake and wires the UI renderer
//   4. After load() resolves, openSignIn/mountSignIn are ready to use

const CLERK_CDN = 'https://cdn.jsdelivr.net/npm/@clerk/clerk-js@5/dist/clerk.browser.js'

let bootPromise: Promise<void> | null = null

export function loadClerk(publishableKey: string): Promise<void> {
  if (bootPromise) return bootPromise

  bootPromise = new Promise<void>((resolve) => {
    const w = window as unknown as {
      Clerk?: {
        load?: (opts: { publishableKey: string }) => Promise<void>
        loaded?: boolean
      }
    }

    // Already fully loaded?
    if (w.Clerk?.loaded) {
      resolve()
      return
    }

    // Script tag already in DOM?
    const existing = document.querySelector<HTMLScriptElement>('script[data-clerk-publishable-key]')
    if (existing) {
      if (w.Clerk) {
        // Script loaded — need to call load() which may already be in progress
        if (!w.Clerk.loaded) {
          w.Clerk.load?.({ publishableKey }).then(resolve).catch(resolve)
        } else {
          resolve()
        }
      } else {
        // Script still loading — wait for Clerk global to appear, then load()
        const interval = setInterval(() => {
          if (w.Clerk) {
            clearInterval(interval)
            if (w.Clerk.loaded) {
              resolve()
            } else {
              w.Clerk.load?.({ publishableKey }).then(resolve).catch(resolve)
            }
          }
        }, 100)
        setTimeout(() => {
          clearInterval(interval)
          resolve()
        }, 10000)
      }
      return
    }

    // Create script tag
    const script = document.createElement('script')
    script.src = CLERK_CDN
    script.setAttribute('data-clerk-publishable-key', publishableKey)
    script.async = true
    script.onload = () => {
      // Clerk global appears async after script load
      const interval = setInterval(() => {
        if (w.Clerk) {
          clearInterval(interval)
          if (w.Clerk.loaded) {
            resolve()
          } else {
            w.Clerk.load?.({ publishableKey }).then(resolve).catch(resolve)
          }
        }
      }, 100)
      setTimeout(() => {
        clearInterval(interval)
        resolve()
      }, 10000)
    }
    script.onerror = () => resolve()
    document.head.appendChild(script)
  })

  return bootPromise
}

export function getClerk() {
  return (window as unknown as { Clerk?: unknown }).Clerk
}

export async function getClerkSession(): Promise<unknown | null> {
  const w = window as unknown as {
    Clerk?: {
      session?: unknown
      client?: { sessions?: unknown[] }
    }
  }
  if (!w.Clerk) return null
  const sessions = w.Clerk.client?.sessions || []
  return w.Clerk.session ?? (sessions.length > 0 ? sessions[0] : null)
}

export async function getClerkToken(opts?: { skipCache?: boolean }): Promise<string | null> {
  const w = window as unknown as {
    Clerk?: {
      session?: { getToken?: (o?: { skipCache?: boolean }) => Promise<string> }
      client?: { sessions?: { getToken?: (o?: { skipCache?: boolean }) => Promise<string> }[] }
    }
  }
  // Clerk.session is the active one; after a redirect back from the Account
  // Portal it can be transiently null while client.sessions is populated (the
  // same reason static/auth.js treats sessions as the durable truth).
  const session = w.Clerk?.session || w.Clerk?.client?.sessions?.[0]
  try {
    const tok = await session?.getToken?.(opts)
    return tok || null
  } catch {
    return null
  }
}

/**
 * Resolve once Clerk has finished loading, or after a bounded wait.
 *
 * apiFetch awaits this before reading a token. Without it, a call issued in the
 * first milliseconds of a page load (history restore, the brains list) reads
 * window.Clerk === undefined, sends no Authorization header, and 401s — which
 * is exactly how the legacy shell's authHeaders() was fixed (static/auth.js
 * awaits its boot promise before deciding the mode).
 */
export function awaitClerkBoot(timeoutMs = 10000): Promise<void> {
  return new Promise<void>((resolve) => {
    if (bootPromise) {
      bootPromise.then(() => resolve()).catch(() => resolve())
      return
    }
    const w = window as unknown as { Clerk?: { loaded?: boolean } }
    if (w.Clerk?.loaded) {
      resolve()
      return
    }
    const started = Date.now()
    const interval = setInterval(() => {
      const c = (window as unknown as { Clerk?: { loaded?: boolean } }).Clerk
      if (c?.loaded || Date.now() - started > timeoutMs) {
        clearInterval(interval)
        resolve()
      }
    }, 50)
  })
}

