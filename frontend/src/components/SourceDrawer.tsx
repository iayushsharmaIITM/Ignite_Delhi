import { useEffect, useState } from "react"
import { apiFetch } from "@/lib/api"

type Props = {
  title: string
  excerpt?: string
  brain: string
  onClose: () => void
}

/**
 * Source drawer (legacy /api/source parity): opens the cited document's full
 * text via /api/source — the app-tier resolver prefers durable provenance and
 * falls back to corpus/tenant exactly like the legacy shell. The probe excerpt
 * from the answer stays visible above the full text.
 */
export function SourceDrawer({ title, excerpt, brain, onClose }: Props) {
  const [full, setFull] = useState<string | null>(null)
  const [origin, setOrigin] = useState<string>("")
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const ac = new AbortController()
    apiFetch(`/api/source?name=${encodeURIComponent(title)}&dataset=${encodeURIComponent(brain)}`, {
      signal: ac.signal,
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => {
        if (!alive) return
        if (d.ok) {
          setFull(d.text || "")
          setOrigin(d.source || "")
        } else {
          setError("unavailable")
        }
      })
      .catch((e) => alive && setError(String(e).slice(0, 120)))
    return () => {
      alive = false
      ac.abort()
    }
  }, [title, brain])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose()
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-y-0 right-0 z-40 w-[420px] max-w-full overflow-y-auto border-l
                  border-border bg-card p-6 shadow-2xl"
      role="dialog"
      aria-label="Cited source"
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        <button
          type="button"
          aria-label="Close source panel"
          className="rounded p-1 text-muted-foreground hover:text-foreground"
          onClick={onClose}
        >
          ✕
        </button>
      </div>
      {excerpt && (
        <div className="mb-4">
          <div className="mb-1 text-[10.5px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
            Cited passage
          </div>
          <pre className="whitespace-pre-wrap rounded-lg border border-border bg-panel-2 p-4 text-[13px] text-foreground/90">
            {excerpt}
          </pre>
        </div>
      )}
      <div className="mb-1 text-[10.5px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
        Full document {origin ? `· ${origin}` : ""}
      </div>
      {error ? (
        <p className="rounded-lg border border-border bg-panel-2 p-4 text-[13px] text-muted-foreground">
          This reference could not be opened ({error}) — the citation stays
          marked unresolved rather than guessed.
        </p>
      ) : full === null ? (
        <p className="rounded-lg border border-border bg-panel-2 p-4 text-[13px] text-muted-foreground">
          Opening…
        </p>
      ) : (
        <pre className="whitespace-pre-wrap rounded-lg border border-border bg-panel-2 p-4 text-[13px] leading-relaxed text-foreground/90">
          {full || "The cited passage is not available for this reference."}
        </pre>
      )}
    </div>
  )
}
