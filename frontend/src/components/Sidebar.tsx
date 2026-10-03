import { useEffect, useMemo, useState } from "react"

// The sidebar is the legacy shell's `aside.shell` DOM (static/shell.js
// buildLinks/chatGroup/renderUser), styled by legacy/deck.css. React only
// replaces the state layer: the same classes mean the same styles, and every
// handler is the pre-port React one. Nav matches legacy exactly (Connectors
// lives in the gear menu, as on :8000).

type ChatSummary = { id: string; title: string; brain: string; at: number }
export type SidebarUser = { nm: string; em: string; initials: string; imageUrl?: string } | null
type Props = {
  mobileOpen?: boolean
  onToggle: () => void
  currentBrain: string
  currentChat: string | null
  view: "chat" | "connectors" | "graph" | "legacy-brains" | "legacy-upload" | "legacy-graph"
  onViewChange: (v: "chat" | "connectors" | "graph" | "legacy-brains" | "legacy-upload" | "legacy-graph") => void
  onBrainChange: (brain: string) => void
  onNewChat: () => void
  onOpenChat: (chatId: string, brain?: string) => void
  chats: ChatSummary[]
  onRefreshChats?: () => void
  onDeleteChat?: (chatId: string, brain?: string) => void
  onDeleteBrainChats?: (brain: string) => void
  onOpenSettings?: () => void
  onOpenAccount?: () => void
  onSignOut?: () => void
  signedIn?: boolean
  authMode?: string
  user?: SidebarUser
}

// Same icons as shell.js buildLinks — paths copied verbatim.
const NAV_ICONS: Record<string, string> = {
  ask: "M21 11.5a8.4 8.4 0 0 1-9 8.4 9 9 0 0 1-3.9-.9L3 21l1.9-4.6A8.4 8.4 0 0 1 12 3.1a8.4 8.4 0 0 1 9 8.4z",
  upload: "M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M4 15v3.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V15",
  brains: "",
  graph: "",
}
const FOLDER_D = "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"
const TRASH_D = "M4 7h16M9 7V5h6v2m-8 0 1 13h8l1-13"
const FILTER_D = "M4 6h16M7 12h10M10 18h4"
const CARET_D = "m9 6 6 6-6 6"

function NavIcon({ name }: { name: string }) {
  const d = NAV_ICONS[name]
  if (name === "brains") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7.5" height="7.5" rx="2" /><rect x="13.5" y="3" width="7.5" height="7.5" rx="2" />
        <rect x="3" y="13.5" width="7.5" height="7.5" rx="2" /><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2" />
      </svg>
    )
  }
  if (name === "graph") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="5" r="2.4" /><circle cx="5" cy="18" r="2.4" /><circle cx="19" cy="18" r="2.4" />
        <path d="M10.4 6.8 6.6 15.7M13.6 6.8l3.8 8.9M7.4 18h9.2" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  )
}

const VIEW_KEY = "kestrel.sidebar.view"
const FOLD_KEY = "kestrel.sidebar.collapsed" // legacy: JSON list of folded brains
const CHAT_CAP = 16
const PER_BRAIN = 5

function readView(): { mode: "brain" | "timeline"; sort: "updated" | "created" } {
  try {
    const v = JSON.parse(localStorage.getItem(VIEW_KEY) || "")
    if (v?.mode === "timeline" || v?.mode === "brain") return { mode: v.mode, sort: v.sort === "created" ? "created" : "updated" }
  } catch { /* first run or quota — legacy defaults */ }
  return { mode: "brain", sort: "updated" }
}

function relTime(ts: number): string {
  if (!ts) return ""
  const s = Math.max(0, (Date.now() - ts) / 1000)
  if (s < 60) return "now"
  if (s < 3600) return Math.round(s / 60) + "m"
  if (s < 86400) return Math.round(s / 3600) + "h"
  return Math.round(s / 86400) + "d"
}

export function Sidebar({
  mobileOpen,
  onToggle,
  currentBrain,
  currentChat,
  view,
  onViewChange,
  onBrainChange,
  onNewChat,
  onOpenChat,
  chats,
  onDeleteChat,
  onDeleteBrainChats,
  onOpenSettings,
  onOpenAccount,
  signedIn,
  authMode,
  user,
}: Props) {
  const [chatView, setChatView] = useState(readView)
  const [viewMenuOpen, setViewMenuOpen] = useState(false)
  const [folded, setFolded] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem(FOLD_KEY) || "[]") } catch { return [] }
  })
  const [armed, setArmed] = useState<string | null>(null) // chat id or "brain:<name>"

  const sorted = useMemo(() => {
    const keyOf = (c: ChatSummary) => (chatView.sort === "created" ? (c as ChatSummary & { created?: number }).created || c.at : c.at)
    return [...chats].sort((a, b) => keyOf(b) - keyOf(a))
  }, [chats, chatView.sort])

  const groups = useMemo(() => {
    const m = new Map<string, ChatSummary[]>()
    sorted.forEach((c) => {
      const k = c.brain || currentBrain
      if (!m.has(k)) m.set(k, [])
      m.get(k)!.push(c)
    })
    return [...m.entries()]
  }, [sorted, currentBrain])

  // The legacy shell closes #sb-viewmenu on any click outside it (or the
  // head-btn) and on Escape — static/shell.js closeViewMenu.
  useEffect(() => {
    if (!viewMenuOpen) return
    const close = (e: MouseEvent) => {
      const t = e.target as HTMLElement | null
      if (t?.closest("#sb-viewmenu") || t?.closest?.(".head-btn")) return
      setViewMenuOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setViewMenuOpen(false) }
    document.addEventListener("click", close)
    document.addEventListener("keydown", onKey)
    return () => { document.removeEventListener("click", close); document.removeEventListener("keydown", onKey) }
  }, [viewMenuOpen])

  const persistView = (v: { mode: "brain" | "timeline"; sort: "updated" | "created" }) => {
    setChatView(v)
    try { localStorage.setItem(VIEW_KEY, JSON.stringify(v)) } catch { /* quota */ }
  }
  const toggleFold = (brain: string) => {
    setFolded((prev) => {
      const next = prev.includes(brain) ? prev.filter((b) => b !== brain) : [...prev, brain]
      try { localStorage.setItem(FOLD_KEY, JSON.stringify(next)) } catch { /* quota */ }
      return next
    })
  }
  // Two-step armed destructive confirm, same anatomy as shell.js chat-del.
  const armOr = (key: string, run: () => void) => {
    if (armed === key) { setArmed(null); run(); return }
    setArmed(key)
  }

  const navItem = (active: boolean, label: string, icon: string, onClick: () => void) => (
    <a
      className={"nav-item" + (active ? " active" : "")}
      href="#"
      onClick={(e) => { e.preventDefault(); onClick() }}
    >
      <NavIcon name={icon} /><span>{label}</span>
    </a>
  )

  const chatRow = (brain: string, c: ChatSummary, timeLabel?: string) => {
    const active = c.id === currentChat && brain === (currentBrain || "demo")
    const title = c.title || "Untitled"
    const armedNow = armed === c.id
    return (
      <div key={brain + "/" + c.id} className={"nav-item chat-item" + (active ? " active" : "")}>
        <a
          className="chat-link"
          href="#"
          title={title}
          onClick={(e) => { e.preventDefault(); onOpenChat(c.id, brain) }}
        >
          <span className="chat-title">{title.slice(0, 30)}</span>
        </a>
        {timeLabel ? <span className="chat-time">{timeLabel}</span> : null}
        <button
          type="button"
          className={"row-del" + (armedNow ? " armed" : "")}
          title={armedNow ? "Click again to delete" : "Delete chat"}
          aria-label="Delete chat"
          onClick={(e) => { e.stopPropagation(); armOr(c.id, () => onDeleteChat?.(c.id, brain)) }}
        >
          {armedNow
            ? <span>×</span>
            : <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d={TRASH_D} /></svg>}
        </button>
      </div>
    )
  }

  let shown = 0
  const listHtml =
    groups.length === 0 ? (
      <div className="chat-empty">No saved chats yet</div>
    ) : chatView.mode === "timeline" ? (
      <>
        {sorted.slice(0, 14).map((c) => {
          const key = (c as ChatSummary & { created?: number }).created || c.at
          return chatRow(c.brain || currentBrain, c, relTime(key))
        })}
        <div className="view-note">Timeline · sorted by {chatView.sort === "created" ? "Created" : "Updated"}</div>
      </>
    ) : (
      <>
        {groups.map(([brain, list]) => {
          if (shown >= CHAT_CAP) return null
          const isFolded = folded.includes(brain)
          const groupKey = "brain:" + brain
          const groupArmed = armed === groupKey
          const rows = isFolded ? null : list.slice(0, PER_BRAIN).map((c) => {
            if (shown >= CHAT_CAP) return null
            shown += 1
            return chatRow(brain, c)
          })
          return (
            <div key={brain}>
              <div
                className={"brain-row" + (isFolded ? " folded" : "")}
                title="Expand or collapse"
                onClick={() => toggleFold(brain)}
              >
                <svg className="caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d={CARET_D} /></svg>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={FOLDER_D} /></svg>
                <span className="brain-name">{brain === "demo" ? "Demo brain" : brain}</span>
                <button
                  type="button"
                  className={"row-del group-del" + (groupArmed ? " armed" : "")}
                  title="Delete all chats in this brain"
                  aria-label="Delete all chats in this brain"
                  onClick={(e) => { e.stopPropagation(); armOr(groupKey, () => onDeleteBrainChats?.(brain)) }}
                >
                  {groupArmed ? <span>× Remove</span> : <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d={TRASH_D} /></svg>}
                </button>
              </div>
              {rows}
            </div>
          )
        })}
        <div className="view-note">Grouped by brain · sorted by {chatView.sort === "created" ? "Created" : "Updated"}</div>
      </>
    )

  return (
    <aside className={"shell" + (mobileOpen ? " open" : "")} aria-label="Kestrel navigation">
      <div className="brand">
        <div className="mark">◆</div>
        <div>
          <div className="name">Kestrel</div>
          <div className="sub">Company Brain</div>
        </div>
        <div className="grow" />
        <button type="button" className="sb-collapse" title="Retract sidebar" aria-label="Retract sidebar" onClick={onToggle}>«</button>
      </div>

      <nav className="nav">
        <div className="nav-label">Workspace</div>
        {navItem(false, "New chat", "ask", onNewChat)}
        {navItem(false, "New brain", "upload", () => onBrainChange("__upload__"))}
        {navItem(view === "legacy-brains", "Brains", "brains", () => onViewChange("legacy-brains"))}
        {navItem(view === "graph" || view === "legacy-graph", "Graph", "graph", () => onBrainChange("__graph__"))}
        <div id="sb-chats">
          <div className="chats-head">
            <span className="nav-label">Chats</span>
            <button
              type="button"
              className="head-btn"
              title="View and sort"
              aria-label="View and sort"
              onClick={() => setViewMenuOpen((v) => !v)}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d={FILTER_D} /></svg>
            </button>
          </div>
          {viewMenuOpen && (
            <div className="pop sb-pop" id="sb-viewmenu">
              <div className="pop-note">View</div>
              <button type="button" onClick={() => { persistView({ ...chatView, mode: "brain" }); setViewMenuOpen(false) }}>
                <span>By brain</span>{chatView.mode === "brain" && <span className="tick">✓</span>}
              </button>
              <button type="button" onClick={() => { persistView({ ...chatView, mode: "timeline" }); setViewMenuOpen(false) }}>
                <span>Timeline</span>{chatView.mode === "timeline" && <span className="tick">✓</span>}
              </button>
              <div className="pop-sep" />
              <div className="pop-note">Sort by</div>
              <button type="button" onClick={() => { persistView({ ...chatView, sort: "updated" }); setViewMenuOpen(false) }}>
                <span>Updated</span>{chatView.sort === "updated" && <span className="tick">✓</span>}
              </button>
              <button type="button" onClick={() => { persistView({ ...chatView, sort: "created" }); setViewMenuOpen(false) }}>
                <span>Created</span>{chatView.sort === "created" && <span className="tick">✓</span>}
              </button>
            </div>
          )}
          {listHtml}
        </div>
      </nav>

      {authMode === "clerk" && (
        <div className="sb-user" id="sb-user">
          {signedIn ? (
            <>
              <button type="button" className="avatar" title={user?.nm || "Account"} onClick={() => onOpenAccount?.()}>
                {user?.imageUrl ? <img src={user.imageUrl} alt="" /> : (user?.initials || "K")}
              </button>
              <button type="button" className="who" onClick={() => onOpenAccount?.()}>
                <div className="nm">{user?.nm || "Kestrel user"}</div>
                <div className="em">{user?.em || ""}</div>
              </button>
              <button type="button" className="gear" aria-label="Settings" onClick={() => onOpenSettings?.()}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3.2" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.55-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h.09a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87v.09a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.55 1z" /></svg>
              </button>
            </>
          ) : (
            <button type="button" className="who" onClick={() => onOpenAccount?.()}>
              <div className="nm">Sign in</div>
            </button>
          )}
        </div>
      )}
    </aside>
  )
}
