import { useEffect, useMemo, useRef, useState } from "react"
import { ChevronLeft } from "lucide-react"
import { t } from "@/lib/i18n"
import { SlideRail } from "@/components/Animations"

// The sidebar keeps the shell's `aside.shell` DOM contract (the class names the
// retired static/shell.js used to build in buildLinks/chatGroup/renderUser),
// styled by design/deck.css. React only replaces the state layer: the same
// classes mean the same styles, and every
// handler is the pre-port React one. Nav matches legacy exactly (Connectors
// lives in the gear menu, as on :8000).

type ChatSummary = { id: string; title: string; brain: string; at: number; created?: number }
export type SidebarUser = { nm: string; em: string; initials: string; imageUrl?: string } | null
type Props = {
  mobileOpen?: boolean
  onToggle: () => void
  currentBrain: string
  currentChat: string | null
  view: "chat" | "brains" | "connectors" | "graph"
  onViewChange: (v: "chat" | "brains" | "connectors" | "graph") => void
  onBrainChange: (brain: string) => void
  onNewChat: () => void
  onOpenChat: (chatId: string, brain?: string) => void
  chats: ChatSummary[]
  /** The server's own words when the chat list could not be read (401/403/5xx). */
  chatsError?: string | null
  /** CH-7: the un-capped count from the server, so a page that hit the limit
   *  can say "showing N of M" instead of looking like the whole history. */
  chatsTotal?: number
  chatsTruncated?: boolean
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

// Server chat rows carry the dataset name, so the demo folder must recognise
// both spellings or it reads "company_brain" where legacy shows "Demo brain".
const DEFAULT_BRAINS = ["company_brain"]
const VIEW_KEY = "kestrel.sidebar.view"
const FOLD_KEY = "kestrel.sidebar.collapsed" // legacy: JSON list of folded brains
const CHAT_CAP = 16
const PER_BRAIN = 5

type ChatSort = "updated" | "created" | "title"
type ChatMode = "brain" | "timeline"

function readView(): { mode: ChatMode; sort: ChatSort } {
  try {
    const v = JSON.parse(localStorage.getItem(VIEW_KEY) || "")
    if (v?.mode === "timeline" || v?.mode === "brain") {
      const sort: ChatSort = v.sort === "created" ? "created" : v.sort === "title" ? "title" : "updated"
      return { mode: v.mode, sort }
    }
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
  chatsError,
  chatsTotal,
  chatsTruncated,
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
  const armTimer = useRef<number>(0)
  const navRef = useRef<HTMLElement>(null)

  // An armed destructive confirm is a state that must expire. Escape, a click
  // anywhere outside the row, and unmount all drop it, so the second click can
  // only ever come from someone who is still looking at the row they armed.
  useEffect(() => {
    if (!armed) return
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setArmed(null) }
    const onClick = (e: MouseEvent) => {
      const el = e.target as HTMLElement | null
      if (el?.closest?.(".row-del, .folder-del, .brain-row")) return
      setArmed(null)
    }
    document.addEventListener("keydown", onKey)
    document.addEventListener("click", onClick, true)
    return () => {
      document.removeEventListener("keydown", onKey)
      document.removeEventListener("click", onClick, true)
    }
  }, [armed])

  useEffect(() => () => { if (armTimer.current) clearTimeout(armTimer.current) }, [])
  // Folders the user expanded past the default per-brain cap. Without this the
  // sidebar showed 5 of 23 chats with no hint that the other 18 existed.
  const [showAllBrains, setShowAllBrains] = useState<string[]>([])

  const sorted = useMemo(() => {
    if (chatView.sort === "title") {
      return [...chats].sort((a, b) =>
        (a.title || "Untitled").localeCompare(b.title || "Untitled", undefined, { sensitivity: "base" })
      )
    }
    const keyOf = (c: ChatSummary) => {
      const ts = chatView.sort === "created" ? (c.created || c.at) : c.at
      return typeof ts === "number" && !Number.isNaN(ts) ? ts : 0
    }
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

  const persistView = (v: { mode: ChatMode; sort: ChatSort }) => {
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
  //
  // It used to arm and never disarm. Nothing reset `armed` except clicking the same
  // row a second time, so a stray first click that the user walked away from left
  // that row permanently one-click-from-deleted — including "delete EVERY chat in
  // this brain" (up to 500 threads). Clicking elsewhere, switching view, or
  // pressing Escape all left it armed, and the × stayed on the row.
  // Every sibling in this app already does it properly (App.tsx clearArmed has a
  // 3.5 s timeout plus Escape; BrainsPage has a 6 s timeout with unmount cleanup),
  // so this is the odd one out, not a house style.
  const armOr = (key: string, run: () => void) => {
    if (armed === key) { setArmed(null); if (armTimer.current) clearTimeout(armTimer.current); run(); return }
    if (armTimer.current) clearTimeout(armTimer.current)
    setArmed(key)
    armTimer.current = window.setTimeout(() => setArmed(null), 4000)
  }

  // Real hrefs + modifier-click support: legacy lets ⌘/Ctrl/middle-click open a
  // nav target in a new tab (shell.js:219-229); href="#" made that impossible.
  const modified = (e: React.MouseEvent) => e.metaKey || e.ctrlKey || e.shiftKey || e.altKey

  const brainQS = currentBrain && currentBrain !== "company_brain" ? `brain=${encodeURIComponent(currentBrain)}` : ""

  const navItem = (active: boolean, label: string, icon: string, onClick: () => void, href: string) => (
    <a
      className={"nav-item" + (active ? " active" : "")}
      href={href}
      onClick={(e) => { if (modified(e)) return; e.preventDefault(); onClick() }}
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
          href={`/?chat=${encodeURIComponent(c.id)}&brain=${encodeURIComponent(brain)}`}
          title={title}
          onClick={(e) => { if (modified(e)) return; e.preventDefault(); onOpenChat(c.id, brain) }}
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
    chatsError ? (
      // Honest state: "No saved chats yet" while the request 401s is the most
      // misleading thing the port could say (shell.css:258 .err).
      <div className="chat-empty err" title={chatsError}>
        {chatsError}
      </div>
    ) : authMode === "clerk" && !signedIn ? (
      // CH-12's corollary: with no session the app does not ask at all, so this
      // panel must not claim the history is empty either. The honest statement
      // is "nothing has been looked at yet", not "you have nothing".
      <div className="chat-empty">{t("nav.sign_in_for_chats", "Sign in to see your chats")}</div>
    ) : groups.length === 0 ? (
      <div className="chat-empty">{t("nav.no_chats", "No saved chats yet")}</div>
    ) : chatView.mode === "timeline" ? (
      <>
        {sorted.slice(0, showAllBrains.includes("*") ? sorted.length : 14).map((c) => {
          const key = chatView.sort === "created" ? (c.created || c.at) : c.at
          return chatRow(c.brain || currentBrain, c, chatView.sort === "title" ? undefined : relTime(key))
        })}
        {sorted.length > 14 && (
          <button
            type="button"
            className="view-more"
            onClick={() => setShowAllBrains((prev) => (prev.includes("*") ? [] : ["*"]))}
          >
            {showAllBrains.includes("*")
              ? t("view.show_less", "Show fewer")
              : t("view.show_all_n", "Show all {n}").replace("{n}", String(sorted.length))}
          </button>
        )}
        <div className="view-note">
          {t("view.timeline", "Timeline")} · {t("view.sorted", "sorted by")}{" "}
          {chatView.sort === "created"
            ? t("view.created", "Created")
            : chatView.sort === "title"
            ? t("view.alphabetical", "Alphabetical (A–Z)")
            : t("view.updated", "Updated")}
        </div>
        {chatsTruncated && (
          <div className="view-note">{`Showing ${chats.length} of ${chatsTotal ?? chats.length} — the rest are older.`}</div>
        )}
      </>
    ) : (
      <>
        {groups.map(([brain, list]) => {
          if (shown >= CHAT_CAP) return null
          const isFolded = folded.includes(brain)
          const groupKey = "brain:" + brain
          const groupArmed = armed === groupKey
          const expanded = showAllBrains.includes(brain)
          const visible = isFolded ? [] : (expanded ? list : list.slice(0, PER_BRAIN))
          const rows = visible.map((c) => {
            if (shown >= CHAT_CAP && !expanded) return null
            shown += 1
            return chatRow(brain, c)
          })
          return (
            <div key={brain} className="brain-group">
              <div
                className={"brain-row" + (isFolded ? " folded" : "")}
                title="Expand or collapse"
                role="button"
                tabIndex={0}
                aria-expanded={!isFolded}
                onClick={() => toggleFold(brain)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault()
                    toggleFold(brain)
                  }
                }}
              >
                <svg className="caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d={CARET_D} /></svg>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={FOLDER_D} /></svg>
                <span className="brain-name">
                  {brain === "demo" || DEFAULT_BRAINS.includes(brain) ? t("brain.demo", "Demo brain") : brain}
                </span>
                {/* The folder says how many it holds, so a capped list never
                    pretends to be the whole history. */}
                <span className="brain-count">{list.length}</span>
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
              {!isFolded && (
                <div className="brain-subchats">
                  {rows}
                  {list.length > PER_BRAIN && (
                    <button
                      type="button"
                      className="view-more"
                      onClick={() => setShowAllBrains((prev) =>
                        prev.includes(brain) ? prev.filter((b) => b !== brain) : [...prev, brain])}
                    >
                      {expanded
                        ? t("view.show_less", "Show fewer")
                        : t("view.show_all_n", "Show all {n}").replace("{n}", String(list.length))}
                    </button>
                  )}
                </div>
              )}
            </div>
          )
        })}
        <div className="view-note">
          {t("view.grouped", "Grouped by brain")} · {t("view.sorted", "sorted by")}{" "}
          {chatView.sort === "created"
            ? t("view.created", "Created")
            : chatView.sort === "title"
            ? t("view.alphabetical", "Alphabetical (A–Z)")
            : t("view.updated", "Updated")}
          {chats.length > 0 ? ` · ${chats.length}` : ""}
          {chatsTruncated ? ` · ${chatsTotal ?? chats.length} total` : ""}
        </div>
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
        <button type="button" className="sb-collapse" title="Retract sidebar" aria-label="Retract sidebar" onClick={onToggle}>
          <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>

      <nav className="nav" ref={navRef}>
        <SlideRail containerRef={navRef} />
        <div className="nav-label">{t("nav.workspace", "Workspace")}</div>
        {navItem(false, t("nav.new_chat", "New chat"), "ask", onNewChat, `/?new=1${brainQS ? "&" + brainQS : ""}`)}
        {/* href="/upload" is for modifier-click (open in a new tab); the route
            redirects into the app, so both paths land on the same flow. */}
        {navItem(false, t("nav.new_brain", "New brain"), "upload", () => onBrainChange("__upload__"), "/upload")}
        {navItem(view === "brains", t("nav.brains", "Brains"), "brains", () => onViewChange("brains"), `/brains`)}
        {navItem(view === "graph", t("nav.graph", "Graph"), "graph", () => onViewChange("graph"), `/graph${brainQS ? "?" + brainQS : ""}`)}
        <div id="sb-chats">
          <div className="chats-head">
            <span className="nav-label">{t("nav.chats", "Chats")}</span>
            <button
              type="button"
              className={"head-btn" + (viewMenuOpen ? " active" : "")}
              title={t("view.toggle", "View and sort")}
              aria-label={t("view.toggle", "View and sort")}
              onClick={() => setViewMenuOpen((v) => !v)}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d={FILTER_D} /></svg>
            </button>
          </div>
          {viewMenuOpen && (
            <div className="pop sb-pop" id="sb-viewmenu" role="menu" aria-label="View and sort">
              <div className="pop-note">{t("view.title", "View")}</div>
              <button type="button" onClick={() => { persistView({ ...chatView, mode: "brain" }); setViewMenuOpen(false) }}>
                <span>{t("view.by_brain", "By brain")}</span>{chatView.mode === "brain" && <span className="tick">✓</span>}
              </button>
              <button type="button" onClick={() => { persistView({ ...chatView, mode: "timeline" }); setViewMenuOpen(false) }}>
                <span>{t("view.timeline", "Timeline")}</span>{chatView.mode === "timeline" && <span className="tick">✓</span>}
              </button>
              <div className="pop-sep" />
              <div className="pop-note">{t("view.sort_by", "Sort by")}</div>
              <button type="button" onClick={() => { persistView({ ...chatView, sort: "updated" }); setViewMenuOpen(false) }}>
                <span>{t("view.updated", "Updated")}</span>{chatView.sort === "updated" && <span className="tick">✓</span>}
              </button>
              <button type="button" onClick={() => { persistView({ ...chatView, sort: "created" }); setViewMenuOpen(false) }}>
                <span>{t("view.created", "Created")}</span>{chatView.sort === "created" && <span className="tick">✓</span>}
              </button>
              <button type="button" onClick={() => { persistView({ ...chatView, sort: "title" }); setViewMenuOpen(false) }}>
                <span>{t("view.alphabetical", "Alphabetical (A–Z)")}</span>{chatView.sort === "title" && <span className="tick">✓</span>}
              </button>
            </div>
          )}
          {listHtml}
        </div>
      </nav>

      {/* The gear is the only door to language, theme, usage, upgrade and
          connectors, so it renders in every mode — but the ACCOUNT area does not.
          This used to carry a "Local mode · No account required" block for
          AUTH_MODE=off, which advertised a no-sign-in path to anyone who reached a
          server booted that way. Sign-in is the product's only entry now; `off`
          survives purely as the verification seam that verify.sh and CI name
          explicitly, and a seam should not come with a label. */}
      <div className="sb-user" id="sb-user">
        {authMode === "clerk" ? (
          signedIn ? (
            <>
              <button type="button" className="avatar" title={user?.nm || "Account"} onClick={() => onOpenAccount?.()}>
                {user?.imageUrl ? <img src={user.imageUrl} alt="" /> : (user?.initials || "K")}
              </button>
              <button type="button" className="who" onClick={() => onOpenAccount?.()}>
                <div className="nm">{user?.nm || "Kestrel user"}</div>
                <div className="em">{user?.em || ""}</div>
              </button>
            </>
          ) : (
            <button type="button" className="who" onClick={() => onOpenAccount?.()}>
              <div className="nm">{t("set.sign_in", "Sign in")}</div>
              <div className="em">{t("set.signed_out_em", "Settings are still available")}</div>
            </button>
          )
        ) : (
          // The verification seam (AUTH_MODE=off, what the battery boots) gets the
          // same row, pointed at the surface that actually works there. The row is
          // never dropped: it used to read "Local mode - No account required", which
          // advertised a no-sign-in path, and deleting the whole block instead was
          // the other wrong answer - the section is the door to settings, usage and
          // connectors in every mode.
          <button type="button" className="who" onClick={() => onOpenSettings?.()}>
            <div className="nm">{t("set.title", "Settings")}</div>
            <div className="em">{t("set.off_em", "Language, theme, usage, connectors")}</div>
          </button>
        )}
        <button
          type="button"
          className="gear"
          title={t("set.title", "Settings")}
          aria-label={t("set.title", "Settings")}
          aria-haspopup="menu"
          onClick={() => onOpenSettings?.()}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3.2" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.55-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h.09a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87v.09a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.55 1z" /></svg>
        </button>
      </div>
    </aside>
  )
}
