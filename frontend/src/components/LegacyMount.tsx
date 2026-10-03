import { useState } from "react"

type Props = {
  /** legacy page path, e.g. "/brains" — same origin in prod, proxied in dev */
  path: string
  label: string
}

/**
 * Phase 9 mount: renders a LEGACY HTML page full-viewport inside the React
 * shell. The React sidebar hides while mounted (App.tsx) so the legacy page's
 * own chrome is the single navigation — no double-nesting. Same-origin in
 * production, so the Clerk session and all cookies apply inside the frame.
 */
export function LegacyMount({ path, label }: Props) {
  const [loaded, setLoaded] = useState(false)
  return (
    <div className="relative h-full w-full">
      {!loaded && (
        <div className="absolute inset-0 grid place-items-center bg-background" aria-hidden>
          <span className="inline-block h-3.5 w-3.5 animate-pulse rounded-full bg-accent/80" />
        </div>
      )}
      <iframe
        src={path}
        title={`${label} (legacy page)`}
        className="h-full w-full border-0 bg-background"
        onLoad={() => setLoaded(true)}
      />
      <div
        className="fixed bottom-4 right-4 z-50 flex items-center gap-2 rounded-full border border-line-2
                   bg-panel/95 px-3.5 py-2 text-[11.5px] text-muted-foreground shadow-lg backdrop-blur"
      >
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-accent" aria-hidden />
        Mounted legacy page: {label}
        <a
          href="/"
          className="ml-1 rounded-full border border-line-2 px-2.5 py-0.5 text-[11px] text-foreground transition-colors duration-150 ease-out hover:border-accent/60 hover:text-accent"
        >
          ⟨ Back to app
        </a>
      </div>
    </div>
  )
}
