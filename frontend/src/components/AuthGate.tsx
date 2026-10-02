import { useEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"
import { resolvedTheme } from "@/theme"
import { t } from "@/lib/i18n"

type Props = {
  children: React.ReactNode
}

declare global {
  interface Window {
    Clerk?: {
      load?: () => Promise<void>
      session?: {
        getToken?: () => Promise<string>
      }
      mountSignIn?: (node: HTMLElement, props?: Record<string, unknown>) => void
      openSignIn?: () => void
      signOut?: () => Promise<void>
      addListener?: (cb: (session: unknown) => void) => () => void
    }
  }
}

export function AuthGate({ children }: Props) {
  const [ready, setReady] = useState(false)
  const [session, setSession] = useState<unknown>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Check for existing session on mount
  useEffect(() => {
    const w = window as unknown as Window
    if (!w.Clerk) {
      // Clerk not loaded — allow access (dev mode)
      setReady(true)
      return
    }

    w.Clerk.load?.()
      .then(() => {
        setSession(w.Clerk?.session ?? null)
        setReady(true)
      })
      .catch(() => {
        setReady(true)
      })
  }, [])

  // Listen for session changes
  useEffect(() => {
    const w = window as unknown as Window
    if (!w.Clerk?.addListener) return
    const unsub = w.Clerk.addListener((s) => {
      setSession(s)
    })
    return unsub
  }, [])

  // Mount Clerk sign-in when no session
  useEffect(() => {
    if (!ready || session) return
    const w = window as unknown as Window
    if (!w.Clerk?.mountSignIn || !containerRef.current) return

    w.Clerk.mountSignIn(containerRef.current, {
      appearance: {
        baseTheme: resolvedTheme() === "dark" ? "dark" : "light",
        variables: {
          colorPrimary: resolvedTheme() === "dark" ? "#e8873a" : "#b45309",
          colorBackground: resolvedTheme() === "dark" ? "#1a1a1a" : "#f7f5f2",
          colorInputBackground: resolvedTheme() === "dark" ? "#212121" : "#ffffff",
          colorText: resolvedTheme() === "dark" ? "#ececec" : "#201d18",
          colorTextSecondary: resolvedTheme() === "dark" ? "#9a9a9a" : "#5f5a52",
          colorBorder: resolvedTheme() === "dark" ? "rgba(255,255,255,0.13)" : "rgba(28,24,16,0.15)",
          borderRadius: "12px",
        },
        elements: {
          formButtonPrimary: "bg-accent text-accent-foreground hover:bg-accent/90",
          socialButtonsBlockButton: "border border-line bg-panel text-foreground hover:bg-wash-2",
          socialButtonsBlockButtonArrow: "text-muted-foreground",
          footerActionLink: "text-accent hover:text-accent-2",
        },
      },
    })
  }, [ready, session])

  // If no Clerk or session exists, render children
  if (!ready || session) {
    return <>{children}</>
  }

  // Full-screen sign-in overlay
  return (
    <div className="relative h-full w-full">
      {/* Blurred app behind */}
      <div className="absolute inset-0 blur-xl" aria-hidden>
        {children}
      </div>

      {/* Overlay */}
      <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
        <div
          className={cn(
            "w-full max-w-md rounded-2xl border border-line bg-panel p-8 shadow-2xl",
          )}
        >
          {/* Logo */}
          <div className="mb-6 flex flex-col items-center gap-3">
            <div className="grid h-14 w-14 place-items-center rounded-xl bg-primary text-2xl text-primary-foreground shadow-lg">
              ◆
            </div>
            <h1 className="text-xl font-semibold tracking-tight text-foreground">
              {t("gate.title")}
            </h1>
            <p className="text-center text-[13px] text-muted-foreground">
              {t("gate.sub")}
            </p>
          </div>

          {/* Clerk sign-in mount point */}
          <div ref={containerRef} className="min-h-[300px]" />

          {/* Fallback if Clerk JS not available */}
          <div className="mt-4 flex flex-col gap-2">
            <button
              type="button"
              onClick={() => {
                const w = window as unknown as Window
                w.Clerk?.openSignIn?.()
              }}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-line bg-wash-3 px-4 py-2.5 text-[13px] font-medium text-foreground transition-colors duration-150 ease-out hover:border-line-2 hover:bg-wash-2"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z" />
              </svg>
              Continue with Google
            </button>
            <button
              type="button"
              onClick={() => {
                const w = window as unknown as Window
                w.Clerk?.openSignIn?.()
              }}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-line bg-wash-3 px-4 py-2.5 text-[13px] font-medium text-foreground transition-colors duration-150 ease-out hover:border-line-2 hover:bg-wash-2"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C6.477 2 2 6.477 2 12c0 4.991 3.657 9.128 8.438 9.879V14.89h-2.54V12h2.54V9.797c0-2.506 1.492-3.89 3.777-3.89 1.094 0 2.238.195 2.238.195v2.46h-1.26c-1.243 0-1.63.771-1.63 1.562V12h2.773l-.443 2.89h-2.33v6.989C18.343 21.129 22 16.99 22 12c0-5.523-4.477-10-10-10z" />
              </svg>
              Continue with Facebook
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
