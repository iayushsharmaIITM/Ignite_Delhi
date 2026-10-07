import { useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { Mail } from "lucide-react"
import { t } from "@/lib/i18n"
import { apiFetch } from "@/lib/api"

export type EmailDraftData = { to?: string; subject: string; body: string }

type Props = {
  draft: EmailDraftData
  busy: boolean
  onBodyChange: (body: string) => void
  onClose: () => void
}

// Opens as a floating modal tile above the rest of the screens (like Settings/Usage/Connectors).
// POST /api/actions/draft fills it, POST /api/actions/send is the approval gate.
export function DraftBox({ draft, busy, onBodyChange, onClose }: Props) {
  const [sending, setSending] = useState(false)
  const sheetRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])

  const copy = () => {
    navigator.clipboard
      .writeText(`Subject: ${draft.subject}\n\n${draft.body}`)
      .then(() => toast.success(t("common.copied", "Copied!")), () => {})
  }
  const mailto = () => {
    window.open(
      `mailto:${encodeURIComponent(draft.to || "")}?subject=${encodeURIComponent(draft.subject)}&body=${encodeURIComponent(draft.body)}`,
      "_self",
    )
  }
  // Self-gating, like every other POST surface in this app.
  const send = async () => {
    if (sending) return
    setSending(true)
    try {
      const r = await apiFetch("/api/actions/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: "email", draft }),
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) {
        // 503 unconfigured / 502 transport — the server's words are the honest state
        toast.error(d.detail || `HTTP ${r.status}`)
        return
      }
      toast.success(d.result?.status || `Sent to ${draft.to || "recipient"}`)
      onClose()
    } catch (e) {
      toast.error("Could not reach the server: " + (e as Error).message)
    } finally {
      setSending(false)
    }
  }

  return (
    <div
      className="km-scrim"
      style={{ zIndex: 90 }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        id="draft"
        ref={sheetRef}
        className="km-sheet max-w-[640px] w-full p-0 overflow-hidden rounded-2xl shadow-2xl border border-border bg-card animate-in fade-in-0 zoom-in-95"
        style={{ display: "block" }}
        role="dialog"
        aria-modal="true"
        aria-label="Email Draft"
      >
        <div className="box border-0 m-0">
          <div className="head flex items-center justify-between px-5 py-3.5 border-b border-border bg-panel-2">
            <div className="flex items-center gap-2">
              <Mail className="h-4 w-4 text-primary" />
              <strong className="text-xs font-semibold tracking-wider text-foreground">
                EMAIL DRAFT{draft.to ? ` · to ${draft.to}` : ""}
              </strong>
            </div>
            <span className="sp flex items-center gap-1.5">
              <button type="button" className="mini" onClick={copy}>{t("src.copy", "Copy")}</button>
              <button type="button" className="mini" onClick={mailto}>Open in mail</button>
              <button type="button" className="mini btn-primary" disabled={busy || sending} onClick={send}>
                {sending ? t("draft.sending", "Sending…") : t("draft.send", "Send")}
              </button>
              <button type="button" className="mini" onClick={onClose}>{t("src.close", "Close")}</button>
            </span>
          </div>
          <div className="p-4 space-y-2.5">
            <div className="flex flex-wrap items-center justify-between text-xs text-muted-foreground px-1 gap-2">
              <span>Subject: <b className="text-foreground">{draft.subject}</b></span>
              {draft.to && <span>Recipient: <b className="text-foreground">{draft.to}</b></span>}
            </div>
            <textarea
              value={draft.body}
              onChange={(e) => onBodyChange(e.target.value)}
              className="w-full min-h-[260px] p-3 text-xs leading-relaxed rounded-lg border border-border bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              spellCheck
              autoFocus
            />
          </div>
        </div>
      </div>
    </div>
  )
}

