import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { Hash, Link2, Lock, MessageSquare, Plug, Plus, RefreshCw, Send, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { SlackAccessDialog } from "@/components/SlackAccessDialog"
import { GoogleAccessDialog } from "@/components/GoogleAccessDialog"
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
type Channel = {
  id: string
  name: string
  private: boolean
  member: boolean
}
type SlackMessage = {
  ts: string
  user: string
  text: string
  ts_date?: string
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

  // Channel explorer & live posting state
  const [activeTeamId, setActiveTeamId] = useState<string | null>(null)
  const [channels, setChannels] = useState<Channel[]>([])
  const [activeChannelId, setActiveChannelId] = useState<string | null>(null)
  const [messages, setMessages] = useState<SlackMessage[]>([])
  const [loadingChannels, setLoadingChannels] = useState(false)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [postText, setPostText] = useState("")
  const [posting, setPosting] = useState(false)
  const [googleDialogOpen, setGoogleDialogOpen] = useState(false)
  const [showAddChannel, setShowAddChannel] = useState(false)
  const [newChannelName, setNewChannelName] = useState("")
  const [addingChannel, setAddingChannel] = useState(false)

  // Import history
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
      .catch((e) => { setStatus({}); setStatusError((e as Error).message) })
    apiFetch("/api/connectors/slack/workspaces")
      .then(async (r) => {
        if (!r.ok) throw new Error(await serverError(r))
        return r.json()
      })
      .then((d) => {
        const wsList = d.workspaces || []
        setWorkspaces(wsList)
        if (wsList.length > 0) {
          setActiveTeamId((curr) => curr || wsList[0].team_id)
        } else {
          setActiveTeamId(null)
          setChannels([])
          setActiveChannelId(null)
          setMessages([])
        }
      })
      .catch(() => setWorkspaces([]))
  }, [])

  useEffect(refresh, [refresh])
  useEffect(() => { setImportBrain((cur) => cur || brain) }, [brain])

  // Fetch channels when active workspace changes
  useEffect(() => {
    if (!activeTeamId) return
    setLoadingChannels(true)
    apiFetch(`/api/connectors/slack/${encodeURIComponent(activeTeamId)}/channels`)
      .then((r) => r.json())
      .then((d) => {
        if (d.ok && Array.isArray(d.channels)) {
          setChannels(d.channels)
          if (d.channels.length > 0) {
            setActiveChannelId((curr) => {
              const exists = d.channels.some((c: Channel) => c.id === curr)
              return exists ? curr : d.channels[0].id
            })
          }
        }
      })
      .catch(() => setChannels([]))
      .finally(() => setLoadingChannels(false))
  }, [activeTeamId])

  // Fetch messages when active channel changes
  useEffect(() => {
    if (!activeTeamId || !activeChannelId) return
    setLoadingMessages(true)
    apiFetch(`/api/connectors/slack/${encodeURIComponent(activeTeamId)}/messages?channel=${encodeURIComponent(activeChannelId)}`)
      .then((r) => r.json())
      .then((d) => {
        if (d.ok && Array.isArray(d.messages)) {
          setMessages(d.messages)
        }
      })
      .catch(() => setMessages([]))
      .finally(() => setLoadingMessages(false))
  }, [activeTeamId, activeChannelId])

  const runImport = async (source: "slack" | "gmail", explicitChannel?: string, explicitTeam?: string) => {
    const targetBrain = importBrain.trim() || "company_brain"
    const channelToUse = (explicitChannel || importChannel).trim()
    if (!targetBrain) { setImportNote("A target brain is required."); return }
    setImporting(source)
    setImportNote("importing…")
    try {
      const r = await apiFetch("/api/connectors/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source,
          brain: targetBrain,
          limit: Math.max(1, Math.min(100, Number(importLimit) || 25)),
          ...(source === "slack" ? { channel: channelToUse, team_id: explicitTeam || activeTeamId || "" } : { query: importQuery.trim() }),
        }),
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) { setImportNote(d.detail || `HTTP ${r.status}`); toast.error(d.detail || "Import failed"); return }
      const failed = Number(d.failed || 0)
      const successMsg = `Imported ${d.imported ?? 0} of ${Number(d.imported || 0) + failed}` +
        (failed ? ` · ${failed} failed` : "") +
        ` → ${targetBrain}`
      setImportNote(successMsg)
      toast.success(successMsg)
    } catch (e) {
      setImportNote("Could not reach the server: " + (e as Error).message)
      toast.error((e as Error).message)
    } finally {
      setImporting("")
    }
  }

  const postSlackMessage = async () => {
    if (!activeTeamId || !activeChannelId || !postText.trim()) return
    setPosting(true)
    try {
      const r = await apiFetch(`/api/connectors/slack/${encodeURIComponent(activeTeamId)}/post`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          channel: activeChannelId,
          text: postText.trim(),
        }),
      })
      const d = await r.json()
      if (!r.ok || !d.ok) throw new Error(d.detail || "Failed to post message")
      toast.success("Posted to Slack!")
      const newMsg: SlackMessage = {
        ts: d.ts || String(Date.now() / 1000),
        user: "You",
        text: postText.trim(),
        ts_date: "Just now",
      }
      setMessages((prev) => [...prev, newMsg])
      setPostText("")
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setPosting(false)
    }
  }

  const createChannel = async () => {
    if (!activeTeamId || !newChannelName.trim()) return
    setAddingChannel(true)
    try {
      const r = await apiFetch(`/api/connectors/slack/${encodeURIComponent(activeTeamId)}/channels`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newChannelName.trim(), private: false }),
      })
      const d = await r.json()
      if (!r.ok || !d.ok) throw new Error(d.detail || "Failed to add channel")
      toast.success(`Added #${d.channel?.name || newChannelName.trim()}`)
      if (d.channel) {
        setChannels((prev) => [...prev, d.channel])
        setActiveChannelId(d.channel.id)
        setImportChannel(d.channel.id)
      }
      setNewChannelName("")
      setShowAddChannel(false)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setAddingChannel(false)
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
  const currentWs = workspaces?.find((w) => w.team_id === activeTeamId)
  const currentChannel = channels.find((c) => c.id === activeChannelId)

  return (
    <div className="flex-1 overflow-y-auto" aria-label="Connectors">
      <div className="mx-auto max-w-[780px] px-6 py-10">
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
            <div className="flex items-center gap-2">
              <Button
                className="rounded-lg font-semibold"
                onClick={() => {
                  if (slackOAuth?.configured && (!workspaces || workspaces.length === 0)) {
                    // transport-exempt: OAuth hand-off is a browser navigation
                    window.location.href = "/api/connectors/slack/connect?mode=read_post&private=1"
                  } else {
                    setDialogOpen(true)
                  }
                }}
              >
                {workspaces && workspaces.length > 0 ? "Add Workspace" : "Connect Slack"}
              </Button>
              {workspaces && workspaces.length > 0 && (
                <Button
                  variant="outline"
                  className="rounded-lg text-xs"
                  onClick={() => setDialogOpen(true)}
                >
                  Configure
                </Button>
              )}
            </div>
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
                <li
                  key={ws.team_id}
                  className={`flex items-center gap-3 px-3.5 py-3 transition-colors ${
                    activeTeamId === ws.team_id ? "bg-accent-dim/40" : ""
                  }`}
                  onClick={() => setActiveTeamId(ws.team_id)}
                >
                  <Link2 className="h-4 w-4 flex-none text-muted-foreground" aria-hidden />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13.5px] font-medium text-foreground">
                      {ws.team_name || ws.team_id}
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      Connected {ws.connected ? new Date(ws.connected).toLocaleDateString() : ""}
                    </div>
                  </div>
                  <div className="flex flex-none items-center gap-2" onClick={(e) => e.stopPropagation()}>
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

          {/* Interactive Channel Explorer & Live Activity */}
          {currentWs && (
            <div className="mt-5 rounded-lg border border-border bg-panel-2/60 p-4">
              <div className="flex items-center justify-between pb-3">
                <div className="flex items-center gap-2">
                  <MessageSquare className="h-4 w-4 text-primary" />
                  <span className="text-[13px] font-semibold text-foreground">
                    Channels in {currentWs.team_name || currentWs.team_id}
                  </span>
                </div>
                {loadingChannels && (
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <RefreshCw className="h-3 w-3 animate-spin" /> Loading channels…
                  </span>
                )}
              </div>

              {/* Channel Tabs */}
              <div className="flex flex-wrap items-center gap-1.5 pb-3">
                {channels.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => {
                      setActiveChannelId(c.id)
                      setImportChannel(c.id)
                    }}
                    className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
                      activeChannelId === c.id
                        ? "bg-primary text-primary-foreground shadow-sm"
                        : "border border-border bg-card text-muted-foreground hover:bg-accent-dim hover:text-foreground"
                    }`}
                  >
                    {c.private ? <Lock className="h-3 w-3" /> : <Hash className="h-3 w-3" />}
                    {c.name}
                  </button>
                ))}

                {!showAddChannel ? (
                  <button
                    type="button"
                    onClick={() => setShowAddChannel(true)}
                    className="inline-flex items-center gap-1 rounded-md border border-dashed border-border px-2.5 py-1 text-xs font-medium text-muted-foreground hover:border-primary hover:text-foreground transition-colors"
                  >
                    <Plus className="h-3 w-3" /> Add channel
                  </button>
                ) : (
                  <div className="inline-flex items-center gap-1 rounded-md border border-border bg-card px-1.5 py-0.5">
                    <span className="text-xs text-muted-foreground font-mono">#</span>
                    <input
                      type="text"
                      value={newChannelName}
                      onChange={(e) => setNewChannelName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault()
                          createChannel()
                        } else if (e.key === "Escape") {
                          setShowAddChannel(false)
                        }
                      }}
                      placeholder="channel-name"
                      className="w-28 bg-transparent px-1 py-0.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none"
                      autoFocus
                    />
                    <Button
                      size="sm"
                      className="h-6 px-2 text-[11px] font-semibold"
                      disabled={addingChannel || !newChannelName.trim()}
                      onClick={createChannel}
                    >
                      {addingChannel ? "…" : "Add"}
                    </Button>
                    <button
                      type="button"
                      className="px-1 text-xs text-muted-foreground hover:text-foreground"
                      onClick={() => setShowAddChannel(false)}
                      aria-label="Cancel"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                )}
              </div>

              {/* Channel Header & Sync Action */}
              {currentChannel && (
                <div className="mt-2 flex items-center justify-between border-t border-border pt-3">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="font-semibold text-foreground">
                      #{currentChannel.name}
                    </span>
                    <span className="text-muted-foreground font-mono text-[11px]">
                      ({currentChannel.id})
                    </span>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={importing === "slack"}
                    onClick={() => runImport("slack", currentChannel.id, currentWs.team_id)}
                    className="h-7 text-xs font-medium gap-1.5"
                  >
                    <RefreshCw className={`h-3 w-3 ${importing === "slack" ? "animate-spin" : ""}`} />
                    {importing === "slack" ? "Syncing…" : "Sync to Brain"}
                  </Button>
                </div>
              )}

              {/* Messages feed */}
              <div className="mt-3 max-h-[220px] overflow-y-auto rounded-md border border-border bg-card p-3 text-xs space-y-2.5">
                {loadingMessages && (
                  <p className="text-center text-muted-foreground py-2">Loading messages…</p>
                )}
                {!loadingMessages && messages.length === 0 && (
                  <p className="text-center italic text-muted-foreground py-2">
                    No messages in this channel yet.
                  </p>
                )}
                {!loadingMessages &&
                  messages.map((m, idx) => (
                    <div key={m.ts || idx} className="rounded border border-border/50 bg-background/60 p-2.5">
                      <div className="flex items-center justify-between text-[11px] text-muted-foreground mb-1">
                        <span className="font-semibold text-foreground">{m.user || "member"}</span>
                        <span>{m.ts_date || ""}</span>
                      </div>
                      <p className="text-foreground leading-relaxed text-[12px]">{m.text}</p>
                    </div>
                  ))}
              </div>

              {/* Live Slack Composer (if read_post mode) */}
              {currentWs.mode === "read_post" && currentChannel && (
                <div className="mt-3 flex items-center gap-2 pt-2 border-t border-border">
                  <input
                    type="text"
                    value={postText}
                    onChange={(e) => setPostText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault()
                        postSlackMessage()
                      }
                    }}
                    placeholder={`Post to #${currentChannel.name}…`}
                    className="flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    aria-label="Slack message text"
                  />
                  <Button
                    size="sm"
                    disabled={posting || !postText.trim()}
                    onClick={postSlackMessage}
                    className="h-7 gap-1 font-semibold text-xs"
                  >
                    <Send className="h-3 w-3" />
                    {posting ? "Posting…" : "Post"}
                  </Button>
                </div>
              )}
            </div>
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
              onClick={() => {
                if (googleOAuth?.configured) {
                  // transport-exempt: OAuth hand-off is a browser navigation
                  window.location.href = "/api/connectors/oauth/google/start"
                } else {
                  setGoogleDialogOpen(true)
                }
              }}
            >
              {googleOAuth?.configured
                ? googleOAuth?.state === "connected"
                  ? "Reconnect Google"
                  : "Connect Google"
                : googleOAuth?.state === "connected"
                ? "Google Workspace Connected"
                : "Authorize Google Workspace"}
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

        {/* Import history into a brain ------------------------------------- */}
        <section className="mt-6 rounded-xl border border-border bg-card p-5">
          <h2 className="text-[15px] font-semibold text-foreground">
            {t("conn.import_title", "Import history into a brain")}
          </h2>
          <p className="mt-1 text-[12.5px] text-muted-foreground">
            {t("conn.import_sub", "Imported messages become citable documents — the same path as an upload.")}
          </p>

          {/* Quick preset channel chips */}
          <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs">
            <span className="text-muted-foreground text-[11px] mr-1">Quick channels:</span>
            {(channels.length > 0 ? channels.slice(0, 6) : [
              { id: "C_DEMO_INC", name: "incident-postmortems" },
              { id: "C_DEMO_ROAD", name: "product-roadmap" },
              { id: "C_DEMO_SEC", name: "security-compliance" },
            ]).map((preset) => (
              <button
                key={preset.id}
                type="button"
                onClick={() => setImportChannel(preset.id)}
                className="rounded-full border border-border bg-secondary/50 px-2 py-0.5 text-[11px] text-foreground hover:bg-secondary transition-colors"
              >
                #{preset.name.replace(/^#/, "")}
              </button>
            ))}
          </div>

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
      </div>

      <SlackAccessDialog open={dialogOpen} onClose={() => { setDialogOpen(false); refresh() }} />
      <GoogleAccessDialog open={googleDialogOpen} onClose={() => { setGoogleDialogOpen(false); refresh() }} />
    </div>
  )
}
