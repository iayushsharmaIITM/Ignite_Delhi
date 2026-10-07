import { useState } from "react"
import { toast } from "sonner"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { Switch } from "@/components/ui/switch"
import { Button } from "@/components/ui/button"
import { apiFetch, getAuthenticatedRedirectUrl } from "@/lib/api"

type Props = { open: boolean; onClose: () => void }

export function SlackAccessDialog({ open, onClose }: Props) {
  const [workspaceName, setWorkspaceName] = useState("")
  const [channelName, setChannelName] = useState("")
  const [customToken, setCustomToken] = useState("")
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [mode, setMode] = useState<"read_post" | "read">("read_post")
  const [priv, setPriv] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  const handleAuthorize = async () => {
    setSubmitting(true)
    try {
      const r = await apiFetch("/api/connectors/slack/authorize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          team_name: workspaceName.trim() || "My Workspace",
          channel_name: channelName.trim() || "general",
          bot_token: customToken.trim(),
          mode,
          private: priv,
        }),
      })
      const d = await r.json()
      if (!r.ok || !d.ok) throw new Error(d.detail || "Failed to authorize Slack")
      toast.success(`Connected ${d.team_name || "Slack workspace"}!`)
      onClose()
    } catch (err) {
      toast.error((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  const handleOAuthRedirect = async () => {
    try {
      // transport-exempt: OAuth hand-off is a browser navigation
      const url = await getAuthenticatedRedirectUrl("/api/connectors/slack/connect", {
        mode,
        private: priv ? "1" : "0",
        team_name: workspaceName.trim() || "My Workspace",
        channel_name: channelName.trim() || "general",
      })
      window.location.href = url
    } catch (err) {
      toast.error((err as Error).message)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-[480px] gap-4 rounded-xl bg-card sm:rounded-xl">
        <DialogHeader>
          <DialogTitle className="text-foreground">Authorize Slack Workspace</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            Connect your team's Slack workspace and channels to Kestrel
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <label className="text-xs font-semibold text-foreground">Workspace Name</label>
            <input
              type="text"
              value={workspaceName}
              onChange={(e) => setWorkspaceName(e.target.value)}
              placeholder="e.g. My Workspace or Engineering Team"
              className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-foreground">Initial Channel</label>
            <div className="relative mt-1">
              <span className="absolute inset-y-0 left-0 flex items-center pl-2.5 text-xs text-muted-foreground">#</span>
              <input
                type="text"
                value={channelName}
                onChange={(e) => setChannelName(e.target.value)}
                placeholder="general, incident-postmortems, dev-team"
                className="w-full rounded-md border border-border bg-background py-1.5 pl-6 pr-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>
        </div>

        <RadioGroup
          value={mode}
          onValueChange={(v) => setMode(v as "read_post" | "read")}
          className="gap-2 pt-1"
        >
          <label
            htmlFor="acc-rp"
            className="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-2.5 has-[button[data-state=checked]]:border-primary has-[button[data-state=checked]]:bg-accent-dim"
          >
            <RadioGroupItem value="read_post" id="acc-rp" className="mt-0.5" />
            <span className="block">
              <span className="text-[13px] font-semibold text-foreground">
                Read and post messages
                <span className="ml-2 rounded-full border border-primary px-1.5 py-px align-middle text-[10px] font-bold text-primary">
                  Recommended
                </span>
              </span>
              <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">
                Kestrel can read channel history and post answers or digests back.
              </span>
            </span>
          </label>

          <label
            htmlFor="acc-ro"
            className="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-2.5 has-[button[data-state=checked]]:border-primary has-[button[data-state=checked]]:bg-accent-dim"
          >
            <RadioGroupItem value="read" id="acc-ro" className="mt-0.5" />
            <span className="block">
              <span className="text-[13px] font-semibold text-foreground">Read messages only</span>
              <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">
                Kestrel can read channel history but never writes anything.
              </span>
            </span>
          </label>
        </RadioGroup>

        <div className="flex items-start gap-3">
          <Switch id="acc-priv" checked={priv} onCheckedChange={setPriv} className="mt-0.5" />
          <label htmlFor="acc-priv" className="cursor-pointer">
            <span className="text-[13px] font-semibold text-foreground">
              Allow private content access
            </span>
            <span className="block text-xs leading-relaxed text-muted-foreground">
              Includes private channels and direct messages
            </span>
          </label>
        </div>

        {/* Optional Custom Slack Bot Token */}
        <div>
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-[11px] font-medium text-primary hover:underline"
          >
            {showAdvanced ? "Hide custom bot token option" : "Have your own Slack Bot Token? (Optional)"}
          </button>
          {showAdvanced && (
            <div className="mt-2 rounded-lg border border-border bg-panel-2/50 p-2.5">
              <label className="text-[11px] font-semibold text-foreground">Slack Bot User Token</label>
              <input
                type="password"
                value={customToken}
                onChange={(e) => setCustomToken(e.target.value)}
                placeholder="Optional Slack bot token"
                className="mt-1 w-full rounded-md border border-border bg-background px-2.5 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <p className="mt-1 text-[10.5px] text-muted-foreground">
                Leave blank for 1-click workspace authorization, or paste a bot token to connect directly to your live Slack organization.
              </p>
            </div>
          )}
        </div>

        <Button
          className="w-full rounded-lg font-semibold"
          disabled={submitting}
          onClick={handleAuthorize}
        >
          {submitting
            ? "Connecting…"
            : customToken.trim()
            ? "Authorize with Custom Token"
            : "Authorize & Connect (Auto Exchange)"}
        </Button>
        <div className="flex items-center justify-between text-xs text-muted-foreground pt-0.5">
          <span>Prefer external consent?</span>
          <button
            type="button"
            className="text-primary hover:underline font-medium"
            onClick={handleOAuthRedirect}
          >
            Launch Slack.com OAuth →
          </button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
