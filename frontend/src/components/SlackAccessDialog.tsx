import { useEffect, useState } from "react"
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
import { apiFetch } from "@/lib/api"

type Props = { open: boolean; onClose: () => void }

export function SlackAccessDialog({ open, onClose }: Props) {
  const [mode, setMode] = useState<"read_post" | "read">("read_post")
  const [priv, setPriv] = useState(false)
  const [configured, setConfigured] = useState<boolean | null>(null)

  useEffect(() => {
    if (!open) return
    apiFetch("/api/connectors/status")
      .then((r) => r.json())
      .then((s) => setConfigured(!!s?.oauth?.slack?.configured))
      .catch(() => setConfigured(false))
  }, [open])

  const connect = () => {
    // transport-exempt: a top-level navigation, not a fetch — the browser
    // follows the server's OAuth redirect and returns through /?connected=slack.
    window.location.href = `/api/connectors/slack/connect?mode=${mode}&private=${priv ? 1 : 0}`
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-[460px] gap-4 rounded-xl bg-card sm:rounded-xl">
        <DialogHeader>
          <DialogTitle className="text-foreground">Configure access</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            Pick which type of access Kestrel will have
          </DialogDescription>
        </DialogHeader>

        <RadioGroup
          value={mode}
          onValueChange={(v) => setMode(v as "read_post" | "read")}
          className="gap-2"
        >
          <label
            htmlFor="acc-rp"
            className="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-3 has-[button[data-state=checked]]:border-primary has-[button[data-state=checked]]:bg-accent-dim"
          >
            <RadioGroupItem value="read_post" id="acc-rp" className="mt-0.5" />
            <span className="block">
              <span className="text-[13.5px] font-semibold text-foreground">
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
            className="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-3 has-[button[data-state=checked]]:border-primary has-[button[data-state=checked]]:bg-accent-dim"
          >
            <RadioGroupItem value="read" id="acc-ro" className="mt-0.5" />
            <span className="block">
              <span className="text-[13.5px] font-semibold text-foreground">Read messages only</span>
              <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">
                Kestrel can read channel history but never writes anything.
              </span>
            </span>
          </label>
        </RadioGroup>

        <div className="flex items-start gap-3">
          <Switch id="acc-priv" checked={priv} onCheckedChange={setPriv} className="mt-0.5" />
          <label htmlFor="acc-priv" className="cursor-pointer">
            <span className="text-[13.5px] font-semibold text-foreground">
              Allow private content access
            </span>
            <span className="block text-xs leading-relaxed text-muted-foreground">
              Includes direct messages (personal agents only) and private channels
            </span>
          </label>
        </div>

        <Button
          className="w-full rounded-lg font-semibold"
          disabled={configured === false}
          onClick={connect}
        >
          {configured === null ? "Checking…" : configured ? "Connect to Slack" : "Slack app not configured"}
        </Button>
        {configured === false && (
          <p className="-mt-2 text-center text-xs text-muted-foreground">
            This instance has no Slack OAuth client yet — the owner must set
            SLACK_CLIENT_ID / SLACK_CLIENT_SECRET first.
          </p>
        )}
      </DialogContent>
    </Dialog>
  )
}
