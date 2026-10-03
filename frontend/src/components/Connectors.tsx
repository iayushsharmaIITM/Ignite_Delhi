import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { Link2, Plug, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { SlackAccessDialog } from "@/components/SlackAccessDialog"
import { apiFetch, serverError } from "@/lib/api"
import { t } from "@/lib/i18n"

type Status = {
  email_send?: boolean
  slack_send?: boolean
  slack_read?: boolean
  gmail_read?: boolean
  oauth?: Record<string, { configured?: boolean; state?: string }>
}
type Workspace = {
  team_id: string
  team_name: string
  scopes: string
  mode: string
  private: boolean
  connected: string
}

function StatusChip({ ok, label }: { ok: boolean | null; label: string }) {
  if (ok === null) return null
  if (ok)
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-ok/40 bg-ok-dim px-2 py-0.5 text-[11px] text-ok">
        <span className="h-1.5 w-1.5 rounded-full bg-ok" aria-hidden />
        {label}
      </span>
    )
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-line-2 bg-panel-2 px-2 py-0.5 text-[11px] text-muted-foreground">
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/60" aria-hidden />
      {label}
    </span>
  )
}

export function Connectors({ brain = "" }: { brain?: string }) {
  const [status, setStatus] = useState<Status | null>(null)
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [armed, setArmed] = useState<string | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)
  // Import history — legacy's connectors modal carried these exact fields
  // (channel id / search + brain + count). Without them the React page could
  // connect an account but never pull anything into a brain.
  const [importBrain, setImportBrain] = useState(brain)
  const [importChannel, setImportChannel] = useState("")
  const [importQuery, setImportQuery] = useState("")
  const [importLimit, setImportLimit] = useState("25")
  const [importNote, setImportNote] = useState("")
  const [importing, setImporting] = useState<"" | "slack" | "gmail">("")

  const refresh = useCallback(() => {
    apiFetch("/api/connectors/status")
      .then(async (r) => {
        if (!r.ok) throw new Error(await serverError(r))
        return r.json()
      })
      .then((d) => { setStatus(d); setStatusError(null) })
      // "Not configured" and "could not ask" are different facts: showing the
      // first when the second is true is how a 401 hides behind a status pill.
      .catch((e) => { setStatus({}); setStatusError((e as Error).message) })
    apiFetch("/api/connectors/slack/workspaces")
      .then(async (r) => {
        if (!r.ok) throw new Error(await serverError(r))
        return r.json()
      })
      .then((d) => setWorkspaces(d.workspaces || []))
      .catch(() => setWorkspaces([]))
  }, [])

  useEffect(refresh, [refresh])
  useEffect(() => { setImportBrain((cur) => cur || brain) }, [brain])

  const runImport = async (source: "slack" | "gmail") => {
    if (!importBrain.trim()) { setImportNote("A target brain is required."); return }
    setImporting(source)
    setImportNote("importing…")
    try {
      const r = await apiFetch("/api/connectors/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source,
          brain: importBrain.trim(),
          limit: Math.max(1, Math.min(100, Number(importLimit) || 25)),
          ...(source === "slack" ? { channel: importChannel.trim() } : { query: importQuery.trim() }),
        }),
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) { setImportNote(d.detail || `HTTP ${r.status}`); return }
      // The server's own numbers, never a hopeful "imported!".
      const failed = Number(d.failed || 0)
      setImportNote(
        `Imported ${d.imported ?? 0} of ${Number(d.imported || 0) + failed}` +
        (failed ? ` · ${failed} failed` : "") +
        ` → ${importBrain.trim()}`,
      )
    } catch (e) {
      setImportNote("Could not reach the server: " + (e as Error).message)
    } finally {
      setImporting("")
    }
  }

  const disconnect = async (ws: Workspace) => {
    if (armed !== ws.team_id) {
      setArmed(ws.team_id)
      return
    }
    setArmed(null)
    try {
      const r = await apiFetch(`/api/connectors/slack/${encodeURIComponent(ws.team_id)}/disconnect`, {
        method: "POST",
      })
      const d = await r.json()
      if (!r.ok || !d.ok) throw new Error(d.detail || "Disconnect failed")
      toast.success(`Disconnected ${ws.team_name || ws.team_id}`)
      refresh()
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  const slackOAuth = status?.oauth?.slack
  const googleOAuth = status?.oauth?.google

  return (
    <div className="flex-1 overflow-y-auto" aria-label="Connectors">
      <div className="mx-auto max-w-[680px] px-6 py-10">
        <h1 className="text-[22px] font-semibold tracking-tight text-foreground">Connectors</h1>
        <p className="mt-1 text-[13.5px] text-muted-foreground">
          Bring external conversations into a brain. Disconnecting stops future syncs —
          already imported messages stay cited.
        </p>
        {statusError && (
          <p className="mt-4 rounded-lg border border-border bg-card px-3.5 py-2.5 text-[12.5px] text-destructive">
            Could not read connector status: {statusError}
          </p>
        )}

        {/* Slack ------------------------------------------------------------ */}
        <section className="mt-8 rounded-xl border border-border bg-card p-5 transition-colors duration-150 ease-out hover:border-accent/40">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="grid h-10 w-10 place-items-center rounded-lg bg-primary/15 text-lg">
                <Plug className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h2 className="text-[15px] font-semibold text-foreground">Slack</h2>
                <p className="text-xs text-muted-foreground">
                  Read channel history, ask questions about it, post answers back.
                </p>
              </div>
            </div>
            <Button className="rounded-lg font-semibold" onClick={() => setDialogOpen(true)}>
              Configure access
            </Button>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <StatusChip
              ok={slackOAuth?.configured ? true : false}
              label={slackOAuth?.configured ? "OAuth ready" : "OAuth not configured"}
            />
            {status?.slack_read && <StatusChip ok label="Workspace connected" />}
            {status?.slack_send && <StatusChip ok label="Post transport" />}
          </div>

          {/* Connected workspaces */}
          {workspaces && workspaces.length > 0 && (
            <ul className="mt-4 divide-y divide-border rounded-lg border border-border" aria-label="Connected Slack workspaces">
              {workspaces.map((ws) => (
                <li key={ws.team_id} className="flex items-center gap-3 px-3.5 py-3">
                  <Link2 className="h-4 w-4 flex-none text-muted-foreground" aria-hidden />
                  <div className="min-w-0">
                    <div className="truncate text-[13.5px] font-medium text-foreground">
                      {ws.team_name || ws.team_id}
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      Connected {ws.connected ? new Date(ws.connected).toLocaleDateString() : ""}
                    </div>
                  </div>
                  <div className="ml-auto flex flex-none items-center gap-2">
                    <Badge variant="secondary" className="text-[11px]">
                      {ws.mode === "read_post" ? "Read & post" : "Read only"}
                    </Badge>
                    {ws.private && (
                      <Badge variant="outline" className="text-[11px]">
                        Private access
                      </Badge>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      className={armed === ws.team_id ? "text-destructive hover:text-destructive" : "text-muted-foreground"}
                      onClick={() => disconnect(ws)}
                    >
                      {armed === ws.team_id ? "Click again to confirm" : "Disconnect"}
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {workspaces !== null && workspaces.length === 0 && (
            <p className="mt-3 text-xs italic text-muted-foreground">
              No workspaces connected yet.
            </p>
          )}
        </section>

        {/* Google ----------------------------------------------------------- */}
        <section className="mt-4 rounded-xl border border-border bg-card p-5 transition-colors duration-150 ease-out hover:border-accent/40">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="grid h-10 w-10 place-items-center rounded-lg bg-wash-2 text-lg">
                <RefreshCw className="h-5 w-5 text-muted-foreground" aria-hidden />
              </div>
              <div>
                <h2 className="text-[15px] font-semibold text-foreground">Google Workspace</h2>
                <p className="text-xs text-muted-foreground">
                  Import Gmail threads and Drive documents into a brain.
                </p>
              </div>
            </div>
            <Button
              variant="secondary"
              className="rounded-lg"
              disabled={!googleOAuth?.configured}
              // transport-exempt: OAuth hand-off is a browser navigation
              onClick={() => (window.location.href = "/api/connectors/oauth/google/start")}
            >
              {googleOAuth?.state === "connected" ? "Reconnect" : "Connect"}
            </Button>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <StatusChip
              ok={googleOAuth?.configured ? true : false}
              label={googleOAuth?.configured ? "OAuth ready" : "OAuth not configured"}
            />
            {status?.gmail_read && <StatusChip ok label="Account connected" />}
            {status?.email_send && <StatusChip ok label="Send transport" />}
          </div>
        </section>
      </div>

      <section className="mt-6 rounded-xl border border-border bg-card p-5">
        <h2 className="text-[15px] font-semibold text-foreground">
          {t("conn.import_title", "Import history into a brain")}
        </h2>
        <p className="mt-1 text-[12.5px] text-muted-foreground">
          {t("conn.import_sub", "Imported messages become citable documents — the same path as an upload.")}
        </p>
        <div className="conn-import mt-3 flex-wrap gap-2">
          <input
            value={importBrain}
            onChange={(e) => setImportBrain(e.target.value)}
            placeholder={t("conn.brain", "target brain")}
            aria-label={t("conn.brain", "target brain")}
          />
          <input
            value={importChannel}
            onChange={(e) => setImportChannel(e.target.value)}
            placeholder={t("conn.channel", "Slack channel id")}
            aria-label={t("conn.channel", "Slack channel id")}
          />
          <input
            value={importQuery}
            onChange={(e) => setImportQuery(e.target.value)}
            placeholder={t("conn.query", "Gmail search (optional)")}
            aria-label={t("conn.query", "Gmail search query")}
          />
          <input
            value={importLimit}
            onChange={(e) => setImportLimit(e.target.value)}
            type="number"
            min={1}
            max={100}
            className="max-w-[84px]"
            aria-label={t("conn.limit", "how many messages")}
          />
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            variant="secondary"
            className="rounded-lg"
            disabled={importing === "slack"}
            onClick={() => void runImport("slack")}
          >
            {importing === "slack" ? t("conn.importing", "Importing…") : t("conn.import_slack", "Import Slack channel")}
          </Button>
          <Button
            variant="secondary"
            className="rounded-lg"
            disabled={importing === "gmail"}
            onClick={() => void runImport("gmail")}
          >
            {importing === "gmail" ? t("conn.importing", "Importing…") : t("conn.import_gmail", "Import Gmail")}
          </Button>
        </div>
        {importNote && <p className="conn-note">{importNote}</p>}
      </section>

      <SlackAccessDialog open={dialogOpen} onClose={() => { setDialogOpen(false); refresh() }} />
    </div>
  )
}
