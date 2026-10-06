import { useState } from "react"
import { toast } from "sonner"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { apiFetch, getAuthenticatedRedirectUrl } from "@/lib/api"

type Props = { open: boolean; onClose: () => void }

export function GoogleAccessDialog({ open, onClose }: Props) {
  const [email, setEmail] = useState("")
  const [token, setToken] = useState("")
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const handleAuthorize = async () => {
    setSubmitting(true)
    try {
      if (!token.trim()) {
        // transport-exempt: OAuth hand-off is a browser navigation
        const url = await getAuthenticatedRedirectUrl("/api/connectors/oauth/google/start")
        window.location.href = url
        return
      }
      const r = await apiFetch("/api/connectors/google/authorize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim(),
          token: token.trim(),
        }),
      })
      const d = await r.json()
      if (!r.ok || !d.ok) throw new Error(d.detail || "Failed to authorize Google Workspace")
      toast.success(`Connected Google Workspace${d.email ? ` (${d.email})` : ""}!`)
      onClose()
    } catch (err) {
      toast.error((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-[460px] gap-4 rounded-xl bg-card sm:rounded-xl">
        <DialogHeader>
          <DialogTitle className="text-foreground">Connect Google Workspace</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            Link Gmail and Google Drive documents for knowledge grounding
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <label className="text-xs font-semibold text-foreground">Google Account Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="e.g. team@company.com"
              className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <div>
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="text-[11px] font-medium text-primary hover:underline"
            >
              {showAdvanced ? "Hide advanced options" : "Have your own OAuth token or service key? (Optional)"}
            </button>
            {showAdvanced && (
              <div className="mt-2 rounded-lg border border-border bg-panel-2/50 p-2.5">
                <label className="text-[11px] font-semibold text-foreground">Google Access Token / Key</label>
                <input
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="Optional Google token or app password"
                  className="mt-1 w-full rounded-md border border-border bg-background px-2.5 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <p className="mt-1 text-[10.5px] text-muted-foreground">
                  Leave blank for instant 1-click workspace connection, or supply an access token to sync directly with Google APIs.
                </p>
              </div>
            )}
          </div>
        </div>

        <Button
          className="w-full rounded-lg font-semibold"
          disabled={submitting}
          onClick={handleAuthorize}
        >
          {submitting
            ? "Connecting…"
            : token.trim()
            ? "Authorize with Custom Token"
            : "Authorize & Connect Google (Auto OAuth)"}
        </Button>
        <p className="-mt-2 text-center text-xs text-muted-foreground">
          Enables importing Gmail threads and Google Drive documents into any knowledge brain.
        </p>
      </DialogContent>
    </Dialog>
  )
}
