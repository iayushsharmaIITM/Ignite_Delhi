import { useState } from "react"
import { toast } from "sonner"
import { t } from "@/lib/i18n"
import { apiFetch } from "@/lib/api"

export type EmailDraftData = { to?: string; subject: string; body: string }

type Props = {
  draft: EmailDraftData
  busy: boolean
  onBodyChange: (body: string) => void
  onClose: () => void
}

// The legacy #draft box (static/index.html CSS, never wired there) completed
// with the P6 APIs: POST /api/actions/draft fills it, POST /api/actions/send
// is the approval gate. Rendered inside #thread-wrap; #draft's CSS defaults to
// display:none, so the open box opts in with an inline display.
export function DraftBox({ draft, busy, onBodyChange, onClose }: Props) {
  const [sending, setSending] = useState(false)
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
  // Self-gating, like every other POST surface in this app. `busy` means "the draft
  // is still being generated" and is false by the time the box can be read, so the
  // Send button was never disabled while its own request was in flight: a double
  // click sent two emails and raised two toasts. This is the explicit approval gate
  // (app.py POST /api/actions/send), so a duplicate is a message the user approved once.
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
    <div id="draft" style={{ display: "block" }}>
      <div className="box">
        <div className="head">
          <strong>EMAIL DRAFT{draft.to ? ` · to ${draft.to}` : ""}</strong>
          <span className="sp">
            <button type="button" className="mini" onClick={copy}>{t("src.copy", "Copy")}</button>
            <button type="button" className="mini" onClick={mailto}>Open in mail</button>
            <button type="button" className="mini" disabled={busy || sending} onClick={send}>{sending ? t("draft.sending", "Sending…") : t("draft.send", "Send")}</button>
            <button type="button" className="mini" onClick={onClose}>{t("src.close", "Close")}</button>
          </span>
        </div>
        <textarea
          value={draft.body}
          onChange={(e) => onBodyChange(e.target.value)}
          spellCheck
        />
      </div>
    </div>
  )
}
