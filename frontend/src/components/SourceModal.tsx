import { useEffect, useRef, useState, type ReactNode } from "react"
import { toast } from "sonner"
import { t } from "@/lib/i18n"
import { apiFetch } from "@/lib/api"

type Props = {
  title: string
  excerpt?: string
  // Which exact document version the answer was produced from. Optional: citations
  // made before the server knew cannot supply one, and then the newest is opened.
  version?: string
  brain: string
  onClose: () => void
}

// Legacy #source-modal (static/index.html openSource): full cited document
// via /api/source, the where-line states the resolver origin honestly, the
// cited passage is highlighted with <mark> when it can be located, Copy
// hands out the raw text, Escape/Close dismiss.
export function SourceModal({ title, excerpt, version, brain, onClose }: Props) {
  const [where, setWhere] = useState("loading…")
  const [body, setBody] = useState<ReactNode>(null)
  const plainRef = useRef("")

  useEffect(() => {
    let alive = true
    const ac = new AbortController()
    const params = new URLSearchParams({ name: title })
    if (brain) params.set("dataset", brain)
    if (version) params.set("document_version_id", version)
    apiFetch(`/api/source?${params.toString()}`, { signal: ac.signal })
      .then((r) => r.json().catch(() => ({})).then((d) => ({ ok: r.ok, d })))
      .then(({ ok, d }) => {
        if (!alive) return
        if (!ok) throw new Error(d.detail || "unavailable")
        const text = d.text || ""
        plainRef.current = text
        // Since corpus/ became the demo brain's alone, anything not from the corpus
        // came out of this brain's own storage — durable or tenant, both "yours".
        setWhere(
          (d.source === "corpus" ? "from the corpus" : "from your upload") +
            " · " + text.length.toLocaleString() + " chars",
        )
        // locate the cited passage (first 90 chars, whitespace-flattened)
        const needle = (excerpt || "").slice(0, 90).replace(/\s+/g, " ").trim()
        const flat = text.replace(/\s+/g, " ")
        const at = needle ? flat.toLowerCase().indexOf(needle.toLowerCase()) : -1
        if (at >= 0) {
          const cut = Math.max(0, at - 20)
          setBody(
            <>
              <span>{text.slice(0, cut)}</span>
              <mark>{text.slice(cut, cut + needle.length + 40)}</mark>
              <span>{text.slice(cut + needle.length + 40)}</span>
            </>,
          )
        } else {
          setBody(text)
        }
      })
      .catch((e) => {
        if (!alive) return
        setWhere("unavailable")
        setBody("Could not open this source: " + String(e?.message || e).slice(0, 120))
      })
    return () => {
      alive = false
      ac.abort()
    }
  }, [title, excerpt, brain, version])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose()
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [onClose])

  return (
    <div
      id="source-modal"
      role="dialog"
      aria-modal="true"
      aria-label="Cited source"
      // Legacy closes the sheet on a backdrop click (index.html:1812-1815).
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="sheet">
        <div className="head">
          <span className="nm" id="src-name">{title}</span>
          <span className="where" id="src-where">{where}</span>
          <span className="sp">
            <button
              type="button"
              id="src-copy"
              onClick={() => {
                navigator.clipboard.writeText(plainRef.current).then(
                  () => toast.success(t("common.copied", "Copied!")),
                  () => {},
                )
              }}
            >
              {t("src.copy", "Copy")}
            </button>
            <button type="button" id="src-close" onClick={onClose}>{t("src.close", "Close")}</button>
          </span>
        </div>
        <pre id="src-body">{body}</pre>
      </div>
    </div>
  )
}
