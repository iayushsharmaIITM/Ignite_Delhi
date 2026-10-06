import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react"
import { ArrowDown, Loader2, X } from "lucide-react"
import { cn, useDialog } from "@/lib/utils"
import { resolvedTheme } from "@/theme"
import { t } from "@/lib/i18n"
import { apiFetch, serverError } from "@/lib/api"

/* ========================================================================
   Animation utility components — ported from legacy shell.css / index.html
   ======================================================================== */

/* TurnRise: applies rise animation to new turns */
export function TurnRise({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("anim-rise", className)}>{children}</div>
}

/* PopMenu: applies pop animation to menus */
export function PopMenu({ children, className, style }: {
  children: ReactNode
  className?: string
  style?: React.CSSProperties
}) {
  return <div className={cn("anim-pop", className)} style={style}>{children}</div>
}

/* SheetModal: applies sheet animation to modals */
export function SheetModal({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("anim-sheet", className)}>{children}</div>
}

/* ========================================================================
   SlideRail — gliding hover rail for the sidebar
   ======================================================================== */

export function SlideRail({ containerRef }: { containerRef: React.RefObject<HTMLElement | null> }) {
  const railRef = useRef<HTMLDivElement>(null)
  const rafRef = useRef(0)

  // body.sb-slide-on suppresses the per-row hover wash while the gliding rail
  // is live (deck.css:195). The component existed but was imported by nobody,
  // so the signature sidebar interaction was simply absent.
  useEffect(() => {
    document.body.classList.add("sb-slide-on")
    return () => document.body.classList.remove("sb-slide-on")
  }, [])

  useEffect(() => {
    const container = containerRef.current
    const rail = railRef.current
    if (!container || !rail) return

    const onMove = (e: MouseEvent) => {
      if (rafRef.current) return
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = 0
        // Measure against the rail's own containing block with rects, not
        // `row.offsetTop`: offsetTop is relative to whichever element happens to be
        // that row's offsetParent, which is not the rail's parent. A chat row is a
        // DIV.nav-item wrapping an A.chat-link, and the old `closest(".nav-item,
        // .brain-row, button, a")` matched the LINK — whose offsetParent is the row —
        // so hovering the chats list parked the rail 8px into the nav at 21px tall
        // while the row it was meant to highlight sat 292px down. That is the "stuck in
        // the upper-left while hovering the chat section" defect.
        const block = (rail.offsetParent ?? container) as HTMLElement
        const blockTop = block.getBoundingClientRect().top
        const under = document.elementFromPoint(e.clientX, e.clientY)
        // Outer row first, so the rail sizes to the row and not to a link inside it.
        const row = under?.closest<HTMLElement>(".nav-item, .brain-row")
          ?? under?.closest<HTMLElement>("button, a") ?? null
        if (row && container.contains(row)) {
          const rr = row.getBoundingClientRect()
          rail.classList.remove("tick")
          rail.style.left = ""
          rail.style.width = ""
          rail.style.top = Math.round(rr.top - blockTop) + "px"
          rail.style.height = Math.round(rr.height) + "px"
          rail.style.opacity = "1"
        } else {
          const y = e.clientY - blockTop
          rail.classList.add("tick")
          rail.style.left = "10px"
          rail.style.width = "46px"
          rail.style.top = Math.round(y - 1) + "px"
          rail.style.height = "2px"
          rail.style.opacity = ".8"
        }
      })
    }

    const onLeave = () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = 0
      }
      if (rail) rail.style.opacity = "0"
    }

    container.addEventListener("mousemove", onMove)
    container.addEventListener("mouseleave", onLeave)
    return () => {
      container.removeEventListener("mousemove", onMove)
      container.removeEventListener("mouseleave", onLeave)
    }
  }, [containerRef])

  return <div ref={railRef} className="sb-slide" aria-hidden="true" />
}

/* ========================================================================
   JumpToLatest — floating pill that appears when scrolled up
   ======================================================================== */

export function JumpToLatest({
  visible,
  onClick,
}: {
  visible: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      className={cn("jump-latest", visible && "visible")}
      onClick={onClick}
      aria-label="Skip to bottom"
      title="Skip to bottom"
    >
      <ArrowDown className="h-4 w-4" />
      <span>Skip to bottom</span>
    </button>
  )
}

/* ========================================================================
   LeftRail — message scrubber with tick marks for jumping to user messages
   ======================================================================== */

export function LeftRail({
  turns,
  onJump,
}: {
  turns: { role: "user" | "bot"; text: string }[]
  onJump: (index: number) => void
}) {
  const [activeIdx, setActiveIdx] = useState<number | null>(null)
  const railRef = useRef<HTMLDivElement>(null)
  const tickRefs = useRef<(HTMLButtonElement | null)[]>([])
  const suppressScrollRef = useRef(false)
  const suppressTimer = useRef<number | null>(null)

  const userIndices = turns.reduce<number[]>((acc, t, i) => {
    if (t.role === "user") acc.push(i)
    return acc
  }, [])

  useEffect(() => {
    const onScroll = () => {
      if (suppressScrollRef.current) return
      const scrollHeight = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)
      const scrollTop = window.scrollY || document.documentElement.scrollTop
      const clientHeight = window.innerHeight || document.documentElement.clientHeight
      if (scrollTop <= 40) {
        setActiveIdx(0)
        return
      }
      if (clientHeight + scrollTop >= scrollHeight - 60) {
        setActiveIdx(userIndices.length - 1)
        return
      }
      const focus = clientHeight * 0.35
      let best: number | null = null
      let bestDist = Infinity
      tickRefs.current.forEach((el, i) => {
        if (!el) return
        const r = el.getBoundingClientRect()
        const dist = Math.abs(r.top + r.height / 2 - focus)
        if (dist < bestDist) {
          bestDist = dist
          best = i
        }
      })
      setActiveIdx(best ?? 0)
    }
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [userIndices.length])

  if (userIndices.length === 0) return null

  return (
    <div ref={railRef} className="left-rail visible" aria-label="Message navigator">
      {userIndices.map((turnIdx, i) => (
        <button
          key={turnIdx}
          ref={(el) => { tickRefs.current[i] = el }}
          type="button"
          className={cn("tick", activeIdx === i && "here")}
          style={{ animation: `railIn .3s ease ${i * 40}ms backwards` }}
          onClick={() => {
            setActiveIdx(i)
            suppressScrollRef.current = true
            if (suppressTimer.current) clearTimeout(suppressTimer.current)
            suppressTimer.current = window.setTimeout(() => {
              suppressScrollRef.current = false
            }, 600)
            onJump(turnIdx)
          }}
          aria-label={`Jump to: ${turns[turnIdx].text.slice(0, 40)}`}
          title={turns[turnIdx].text.slice(0, 60)}
        />
      ))}
    </div>
  )
}

/* ========================================================================
   RestoreOverlay — full-screen overlay during chat restore
   ======================================================================== */

export function RestoreOverlay({ visible }: { visible: boolean }) {
  if (!visible) return null
  return (
    <div className="restore-overlay" role="status" aria-label="Restoring chat">
      <div className="restore-card">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span>Restoring chat…</span>
      </div>
    </div>
  )
}

/* ========================================================================
   SwitchFx — dim + spinner during chat switch
   ======================================================================== */

export function SwitchFx({ visible }: { visible: boolean }) {
  if (!visible) return null
  return (
    <div className="switch-fx visible" aria-hidden="true">
      <div className="big" />
    </div>
  )
}

/* ========================================================================
   WorkingLog — real engine steps with measured durations
   ======================================================================== */

export type WorkStep = { label: string; ms?: number }

export function WorkingLog({
  steps,
  elapsed,
  streaming,
  stopped,
}: {
  steps: WorkStep[]
  elapsed: number
  streaming: boolean
  stopped?: boolean
}) {
  const [collapsed, setCollapsed] = useState(false)

  useEffect(() => {
    if (!streaming) setCollapsed(true)
  }, [streaming])

  return (
    <div className={cn("working-log", collapsed && "collapsed")}>
      <div
        className={cn("working-head", !streaming && "toggle")}
        onClick={() => !streaming && setCollapsed((c) => !c)}
        role={!streaming ? "button" : undefined}
        tabIndex={!streaming ? 0 : undefined}
        onKeyDown={(e) => {
          if (!streaming && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault()
            setCollapsed((c) => !c)
          }
        }}
      >
        {streaming && <span className="spin" />}
        <span className="w-elapsed">
          {streaming ? `Working · ${elapsed.toFixed(1)}s` : `Worked · ${elapsed.toFixed(1)}s`}
        </span>
        {stopped && <span className="w-stopped">· stopped</span>}
      </div>
      {steps.map((s, i) => (
        <div key={i} className={cn("w-step", streaming && i === steps.length - 1 ? "live" : "done")}>
          {streaming && i === steps.length - 1 ? s.label : `✓ ${s.label}${s.ms != null ? ` · ${(s.ms / 1000).toFixed(1)}s` : ""}`}
        </div>
      ))}
    </div>
  )
}

/* ========================================================================
   SuggestionChips — demo / generic suggestion chips
   ======================================================================== */

export function SuggestionChips({
  chips,
  onSelect,
}: {
  chips: { icon?: ReactNode; label: string; query: string }[]
  onSelect: (query: string) => void
}) {
  return (
    <div className="suggestion-chips">
      {chips.map((c, i) => (
        <button key={i} type="button" className="chip" onClick={() => onSelect(c.query)}>
          {c.icon}
          <span>{c.label}</span>
        </button>
      ))}
    </div>
  )
}

/* ========================================================================
   Watermark — home page giant diamond
   ======================================================================== */

export function Watermark() {
  return (
    <div className="watermark" aria-hidden="true">
      ◆
    </div>
  )
}

/* ========================================================================
   AuthGate — covers the app until Clerk session exists
   ======================================================================== */

export function AuthGate({
  visible,
  children,
}: {
  visible: boolean
  children?: ReactNode
}) {
  const mountRef = useRef<HTMLDivElement>(null)
  const [mountFailed, setMountFailed] = useState(false)

  // Port of the legacy gate (static/index.html:2165-2211): mount the sign-in
  // CARD inline inside #clerk-mount, retrying while Clerk's renderer catches up
  // with load(). The previous React version called Clerk.openSignIn() behind a
  // blind 10s poll instead — which left an empty "Sign in to Kestrel" card with
  // a modal floating over it, and no inline fallback at all when the modal
  // could not open.
  useEffect(() => {
    if (!visible) return
    const el = mountRef.current
    if (!el) return
    const w = window as unknown as {
      Clerk?: {
        loaded?: boolean
        client?: { sessions?: unknown[] }
        mountSignIn?: (node: HTMLElement, opts?: Record<string, unknown>) => void
        unmountSignIn?: (node: HTMLElement) => void
        openSignIn?: (opts?: Record<string, unknown>) => void
      }
    }
    let tries = 30
    let timer: ReturnType<typeof setTimeout> | null = null
    const tryMount = () => {
      const clerk = w.Clerk
      if (!clerk?.loaded || !clerk.mountSignIn) {
        if (tries-- > 0) { timer = setTimeout(tryMount, 300); return }
        // Last resort: the modal, or say so instead of showing a blank card.
        if (clerk?.openSignIn) clerk.openSignIn({ appearance: appearanceProps() })
        else setMountFailed(true)
        return
      }
      try {
        clerk.mountSignIn(el, { appearance: appearanceProps() })
      } catch {
        if (tries-- > 0) { timer = setTimeout(tryMount, 300); return }
        setMountFailed(true)
      }
    }
    tryMount()
    return () => { if (timer) clearTimeout(timer) }
  }, [visible])

  // A theme switch must re-render Clerk's card or it keeps the old palette.
  useEffect(() => {
    if (!visible) return
    const onTheme = () => {
      const w = window as unknown as {
        Clerk?: { unmountSignIn?: (n: HTMLElement) => void; mountSignIn?: (n: HTMLElement, o?: Record<string, unknown>) => void }
      }
      const el = mountRef.current
      if (!el) return
      try { w.Clerk?.unmountSignIn?.(el) } catch { /* not mounted */ }
      try { w.Clerk?.mountSignIn?.(el, { appearance: appearanceProps() }) } catch { /* retry loop owns it */ }
    }
    window.addEventListener("kestrel:theme", onTheme)
    return () => window.removeEventListener("kestrel:theme", onTheme)
  }, [visible])

  function appearanceProps() {
    const light = resolvedTheme() === "light"
    const variables = light
      ? {
          colorBackground: "#ffffff",
          colorText: "#201d18",
          colorForeground: "#201d18",
          colorInputBackground: "#f3f1ec",
          colorInputText: "#201d18",
          colorPrimary: "#b45309",
          colorPrimaryForeground: "#ffffff",
          colorMutedForeground: "#5f5a52",
          colorBorder: "rgba(28,24,16,.15)",
          header: { display: "none" },
        }
      : {
          colorBackground: "#232323",
          colorText: "#e9e9e9",
          colorForeground: "#e9e9e9",
          colorInputBackground: "#2b2b2b",
          colorInputText: "#e9e9e9",
          colorPrimary: "#e8863b",
          colorPrimaryForeground: "#161616",
          colorMutedForeground: "#9b9b9b",
          colorBorder: "rgba(255,255,255,.13)",
          header: { display: "none" },
        }

    return {
      variables,
      elements: {
        formButtonPrimary: "bg-accent text-accent-foreground hover:bg-accent/90",
        socialButtonsBlockButton: "border border-line bg-panel text-foreground hover:bg-wash-2",
        socialButtonsBlockButtonArrow: "text-muted-foreground",
        footerActionLink: "text-accent hover:text-accent-2",
      },
    } as Record<string, unknown>
  }

  if (!visible) return null
  return (
    <div className="auth-gate">
      <div className="auth-card">
        <div
          style={{
            width: 34,
            height: 34,
            borderRadius: 9,
            background: "linear-gradient(155deg,#f49d54,#d96f1f 78%)",
            display: "grid",
            placeItems: "center",
            color: "#161616",
            fontSize: 14,
            margin: "0 auto 14px",
          }}
        >
          ◆
        </div>
        <div className="auth-title">{t("gate.title", "Sign in to Kestrel")}</div>
        <div className="auth-sub">{t("gate.sub", "Your company's answers, grounded in your documents.")}</div>
        {/* Legacy #clerk-mount: Clerk renders the form here, inside our card. */}
        <div id="clerk-mount" ref={mountRef} />
        {mountFailed && (
          <p className="auth-sub" role="alert">
            Could not load the sign-in form. Check the network connection and reload.
          </p>
        )}
        {children}
      </div>
    </div>
  )
}

/* ========================================================================
   SettingsMenu — popover panel for language, theme, usage, etc.
   ======================================================================== */

export function SettingsMenu({
  open,
  onClose,
  onLanguage,
  onTheme,
  onUsage,
  onUpgrade,
  onConnectors,
  onAccount,
  onSignOut,
  signedIn,
}: {
  open: boolean
  onClose: () => void
  onLanguage: () => void
  onTheme: () => void
  onUsage: () => void
  onUpgrade: () => void
  onConnectors?: () => void
  onAccount: () => void
  onSignOut: () => void
  signedIn: boolean
}) {
  const ref = useRef<HTMLDivElement>(null)

  // deck.css makes .settings-pop position:fixed with NO offsets — legacy
  // computes them from the gear's rect (shell.js:581-585). Without this the
  // menu rendered at its static position, i.e. wherever that happened to be.
  useLayoutEffect(() => {
    if (!open) return
    const menu = ref.current
    if (!menu) return
    const gear = document.querySelector<HTMLElement>(".sb-user .gear")
    const r = gear?.getBoundingClientRect()
    menu.style.left = "12px"
    menu.style.bottom = r ? `${Math.max(10, window.innerHeight - r.top + 8)}px` : "72px"
  }, [open])

  // The legacy pop closes on any click outside it (or the gear) and on Escape
  // (shell.js:1013-1018). `onClose` used to be accepted and ignored.
  useEffect(() => {
    if (!open) return
    const onDocClick = (e: MouseEvent) => {
      const el = e.target as HTMLElement | null
      if (el?.closest(".settings-pop") || el?.closest(".sub-pop") || el?.closest(".sb-user .gear")) return
      onClose()
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    document.addEventListener("click", onDocClick)
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("click", onDocClick)
      document.removeEventListener("keydown", onKey)
    }
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="settings-pop" role="menu" aria-label="Settings" ref={ref}>
      <button type="button" className="set-item" onClick={onLanguage} role="menuitem">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18z"/></svg>
        <span>{t("set.language", "Language")}</span>
        <svg className="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 6 6 6-6 6"/></svg>
      </button>
      <button type="button" className="set-item" onClick={onTheme} role="menuitem">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor" stroke="none"/></svg>
        <span>{t("set.theme", "App theme")}</span>
        <svg className="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 6 6 6-6 6"/></svg>
      </button>
      <div className="set-sep" />
      <button type="button" className="set-item" onClick={onUsage} role="menuitem">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M4 20V10M10 20V4M16 20v-7M20 20H4"/></svg>
        <span>{t("set.usage", "Usage stats")}</span>
      </button>
      <button type="button" className="set-item" onClick={onUpgrade} role="menuitem">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M5 15c-1.5 1.5-2 5-2 5s3.5-.5 5-2M14 4c3-2 7-1 7-1s1 4-1 7l-6 6-4-4 4-6z"/><circle cx="14.5" cy="9.5" r="1.4"/></svg>
        <span>{t("set.upgrade", "Upgrade")}</span>
      </button>
      {onConnectors && (
        <button type="button" className="set-item" onClick={onConnectors} role="menuitem">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M9 7v10M15 7v10M6 4h12M6 20h12" /><circle cx="9" cy="12" r="2.6" /><circle cx="15" cy="12" r="2.6" /></svg>
          <span>{t("set.connectors", "Connectors")}</span>
        </button>
      )}
      {signedIn && (
        <>
          <div className="set-sep" />
          <button type="button" className="set-item" onClick={onAccount} role="menuitem">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-3.5 4.5-5 8-5s6.5 1.5 8 5"/></svg>
            <span>{t("set.account", "Manage account")}</span>
          </button>
          <button type="button" className="set-item" onClick={onSignOut} role="menuitem">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 17l5-5-5-5M15 12H3"/></svg>
            <span>{t("set.signout", "Disconnect")}</span>
          </button>
        </>
      )}
    </div>
  )
}

/* ========================================================================
   ExportMenu — conversation export options
   ======================================================================== */

export function ExportMenu({
  open,
  onExportMd,
  onExportTxt,
  onExportDocx,
  onExportPdf,
  onCopyTranscript,
}: {
  open: boolean
  onClose?: () => void
  onExportMd: () => void
  onExportTxt: () => void
  onExportDocx: () => void
  onExportPdf: () => void
  onCopyTranscript: () => void
}) {
  if (!open) return null
  return (
    <div className="export-menu" role="menu" aria-label="Export conversation">
      <div className="pop-note">Export</div>
      <button type="button" onClick={onExportMd} role="menuitem">Markdown</button>
      <button type="button" onClick={onExportTxt} role="menuitem">Plain text</button>
      <button type="button" onClick={onExportDocx} role="menuitem">Word document</button>
      <button type="button" onClick={onExportPdf} role="menuitem">PDF</button>
      <div className="pop-sep" />
      <button type="button" onClick={onCopyTranscript} role="menuitem">Copy transcript</button>
    </div>
  )
}

/* ========================================================================
   ViewMenu — Brain/Timeline mode + Updated/Created sort
   ======================================================================== */

export function ViewMenu({
  open,
  mode,
  sort,
  onModeChange,
  onSortChange,
}: {
  open: boolean
  mode: "brain" | "timeline"
  sort: "updated" | "created"
  onClose?: () => void
  onModeChange: (m: "brain" | "timeline") => void
  onSortChange: (s: "updated" | "created") => void
}) {
  if (!open) return null
  return (
    <div className="view-menu" role="menu" aria-label="View and sort">
      <div className="view-note">View</div>
      <button type="button" className="view-item" onClick={() => onModeChange("brain")} role="menuitem">
        <span>By brain</span>
        {mode === "brain" && <span className="tick">✓</span>}
      </button>
      <button type="button" className="view-item" onClick={() => onModeChange("timeline")} role="menuitem">
        <span>Timeline</span>
        {mode === "timeline" && <span className="tick">✓</span>}
      </button>
      <div className="view-sep" />
      <div className="view-note">Sort by</div>
      <button type="button" className="view-item" onClick={() => onSortChange("updated")} role="menuitem">
        <span>Updated</span>
        {sort === "updated" && <span className="tick">✓</span>}
      </button>
      <button type="button" className="view-item" onClick={() => onSortChange("created")} role="menuitem">
        <span>Created</span>
        {sort === "created" && <span className="tick">✓</span>}
      </button>
    </div>
  )
}

/* ========================================================================
   MessageActions — copy, email, steps, chat update, thumbs
   ======================================================================== */

export function MessageActions({
  onCopy,
  onEmail,
  onSteps,
  onChatUpdate,
  onThumbsUp,
  onThumbsDown,
  time,
}: {
  onCopy: () => void
  onEmail: () => void
  onSteps: () => void
  onChatUpdate: () => void
  onThumbsUp: () => void
  onThumbsDown: () => void
  time: string
}) {
  const [copied, setCopied] = useState(false)
  const [fb, setFb] = useState<"up" | "down" | null>(null)

  return (
    <div className="msg-acts">
      <button
        type="button"
        aria-label="Copy answer"
        title="Copy answer"
        className={cn(copied && "copied")}
        onClick={async () => {
          await onCopy()
          setCopied(true)
          setTimeout(() => setCopied(false), 1300)
        }}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>
      </button>
      <button type="button" aria-label="Email draft" title="Email draft" onClick={onEmail}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><rect x="2.5" y="4.5" width="19" height="15" rx="2"/><path d="m3 6 9 6.5L21 6"/></svg>
      </button>
      <button type="button" aria-label="Next steps" title="Next steps" onClick={onSteps}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 6l1.4 1.4L8 4.6"/><path d="M4 12l1.4 1.4L8 10.6"/><path d="M4 18l1.4 1.4L8 16.6"/></svg>
      </button>
      <button type="button" aria-label="Chat update" title="Chat update" onClick={onChatUpdate}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9 9 0 0 1-3.9-.9L3 21l1.9-4.6A8.4 8.4 0 0 1 12 3.1a8.4 8.4 0 0 1 9 8.4z"/></svg>
      </button>
      <button
        type="button"
        aria-label="Helpful"
        title="Helpful"
        className={cn(fb === "up" && "fb-on")}
        onClick={() => {
          setFb(fb === "up" ? null : "up")
          onThumbsUp()
        }}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M7 11v9M7 11l4-7c1.2 0 2 .9 2 2v4h5.2a1.8 1.8 0 0 1 1.8 2.1l-1 5.5A2 2 0 0 1 17 19H7"/></svg>
      </button>
      <button
        type="button"
        aria-label="Not helpful"
        title="Not helpful"
        className={cn(fb === "down" && "fb-on")}
        onClick={() => {
          setFb(fb === "down" ? null : "down")
          onThumbsDown()
        }}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M17 13V4M17 13l-4 7c-1.2 0-2-.9-2-2v-4H5.8a1.8 1.8 0 0 1-1.8-2.1l1-5.5A2 2 0 0 1 7 5h10"/></svg>
      </button>
      <span className="time">{time}</span>
    </div>
  )
}

/* ========================================================================
   Usage + Upgrade modals — legacy .km-scrim/.km-sheet (deck.css:407-460)
   ========================================================================
   Both surfaces existed in the stylesheets and in the legacy shell
   (shell.js:640-704) while the React settings menu answered them with a
   toast. The keys (usage.*, up.*) and the endpoint (/api/usage) were already
   there too, unused. */

export type UsageModalProps = { open: boolean; onClose: () => void }

type UsageRow = {
  feature: string
  brain: string
  model: string
  calls: number
  prompt_tokens: number
  completion_tokens: number
  total_ms: number
}

export function UsageModal({ open, onClose }: UsageModalProps) {
  const [rows, setRows] = useState<UsageRow[]>([])
  const [state, setState] = useState<"loading" | "ready" | "error">("loading")
  const [error, setError] = useState("")

  useEffect(() => {
    if (!open) return
    setState("loading")
    apiFetch("/api/usage")
      .then(async (r) => {
        if (!r.ok) throw new Error(await serverError(r))
        return r.json()
      })
      .then((d) => {
        setRows(d.usage || [])
        setState("ready")
      })
      .catch((e) => {
        setError((e as Error).message)
        setState("error")
      })
  }, [open])

  const sheetRef = useDialog<HTMLDivElement>(open, onClose)

  if (!open) return null
  const calls = rows.reduce((n, r) => n + Number(r.calls || 0), 0)
  const tokens = rows.reduce(
    (n, r) => n + Number(r.prompt_tokens || 0) + Number(r.completion_tokens || 0), 0)
  const ms = rows.reduce((n, r) => n + Number(r.total_ms || 0), 0)

  return (
    <div className="km-scrim" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="km-sheet" ref={sheetRef} tabIndex={-1} role="dialog" aria-modal="true"
           aria-label={t("usage.title", "Usage stats")}>
        <div className="km-head">
          <h2>{t("usage.title", "Usage stats")}</h2>
          <button type="button" className="km-x" onClick={onClose} aria-label={t("src.close", "Close")}>
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <p className="km-sub">{t("usage.sub", "Last 30 days · estimated tokens")}</p>
        {state === "loading" && <p className="u-empty">{t("usage.loading", "Loading…")}</p>}
        {state === "error" && <p className="u-empty err">{error}</p>}
        {state === "ready" && rows.length === 0 && (
          <p className="u-empty">{t("usage.empty", "No model calls recorded yet.")}</p>
        )}
        {state === "ready" && rows.length > 0 && (
          <>
            <table className="u-table">
              <thead>
                <tr>
                  <th>{t("usage.feature", "Feature")}</th>
                  <th>{t("usage.brain", "Brain")}</th>
                  <th>{t("usage.model", "Model")}</th>
                  <th className="num">{t("usage.calls", "Calls")}</th>
                  <th className="num">{t("usage.tokens", "Tokens")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={`${r.feature}-${r.brain}-${r.model}-${i}`}>
                    <td>{r.feature}</td>
                    <td>{r.brain}</td>
                    <td>{r.model}</td>
                    <td className="num">{r.calls}</td>
                    <td className="num">{Number(r.prompt_tokens) + Number(r.completion_tokens)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="u-total">
              <span>{t("usage.calls", "Calls")}: <b>{calls}</b></span>
              <span>{t("usage.tokens", "Tokens")}: <b>{tokens}</b></span>
              <span>{t("usage.time", "Time")}: <b>{(ms / 1000).toFixed(1)}s</b></span>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

const TIERS = [
  { key: "free", price: 0, hot: false, current: true },
  { key: "pro", price: 50, hot: true, current: false },
  { key: "biz", price: 99, hot: false, current: false },
] as const

export function UpgradeModal({ open, onClose }: UsageModalProps) {
  const sheetRef = useDialog<HTMLDivElement>(open, onClose)

  if (!open) return null
  return (
    <div className="km-scrim" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="km-sheet" ref={sheetRef} tabIndex={-1} role="dialog" aria-modal="true"
           aria-label={t("set.upgrade", "Upgrade")}>
        <div className="km-head">
          <h2>{t("set.upgrade", "Upgrade")}</h2>
          <button type="button" className="km-x" onClick={onClose} aria-label={t("src.close", "Close")}>
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <p className="km-sub">{t("upg.sub", "Simple plans that scale with your company brain.")}</p>
        <div className="tiers">
          {TIERS.map((tier) => (
            <div className={"tier" + (tier.hot ? " hot" : "")} key={tier.key}>
              <div className="tn">{t(`up.${tier.key}`, tier.key)}</div>
              <div className="tp">
                ${tier.price}<small>{t("up.per_mo", "/mo")}</small>
              </div>
              <ul>
                {[1, 2, 3].map((n) => (
                  <li key={n}>{t(`up.${tier.key}_f${n}`, "")}</li>
                ))}
              </ul>
              {/* Honest: these plans are not purchasable yet (legacy shows the
                  same disabled buttons — shell.js:682-704). */}
              <button type="button" className={"tbtn" + (tier.hot ? " hot" : "")} disabled>
                {tier.current ? t("up.current", "Current plan") : t("up.soon", "Coming soon")}
              </button>
            </div>
          ))}
        </div>
        <p className="km-note">{t("up.note", "Plans are not purchasable yet — nothing is charged.")}</p>
      </div>
    </div>
  )
}
