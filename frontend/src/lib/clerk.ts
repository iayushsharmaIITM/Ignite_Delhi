// Clerk loader — loads the Clerk JS bundle from CDN and boots it.
// Port of the legacy auth.js init() for the React app.

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

    // Already loaded?
    if (w.Clerk?.loaded) {
      resolve()
      return
    }

    // Script tag already in DOM?
    const existing = document.querySelector<HTMLScriptElement>('script[data-clerk-publishable-key]')
    if (existing && w.Clerk) {
      w.Clerk.load?.({ publishableKey }).then(resolve).catch(resolve)
      return
    }

    // Create script tag
    const script = document.createElement('script')
    script.src = CLERK_CDN
    script.setAttribute('data-clerk-publishable-key', publishableKey)
    script.async = true
    script.onload = () => {
      w.Clerk?.load?.({ publishableKey }).then(resolve).catch(resolve)
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
  // A client holding sessions IS signed in (same logic as legacy auth.js)
  const sessions = w.Clerk.client?.sessions || []
  return w.Clerk.session ?? (sessions.length > 0 ? sessions[0] : null)
}

export async function getClerkToken(): Promise<string | null> {
  const w = window as unknown as {
    Clerk?: {
      session?: { getToken?: () => Promise<string> }
    }
  }
  try {
    const tok = await w.Clerk?.session?.getToken?.()
    return tok || null
  } catch {
    return null
  }
}
