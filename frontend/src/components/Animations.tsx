import { useEffect, useRef, useState, type ReactNode } from "react"
import { ArrowDown, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { resolvedTheme } from "@/theme"

/* ========================================================================
   Animation utility components — ported from legacy shell.css / index.html
   ======================================================================== */

/* TurnRise: applies rise animation to new turns */
export function TurnRise({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("anim-rise", className)}>{children}</div>
}

/* PopMenu: applies pop animation to menus */
export function PopMenu({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("anim-pop", className)}>{children}</div>
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

  useEffect(() => {
    const container = containerRef.current
    const rail = railRef.current
    if (!container || !rail) return

    const onMove = (e: MouseEvent) => {
      if (rafRef.current) return
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = 0
        const rect = container.getBoundingClientRect()
        const y = e.clientY - rect.top + container.scrollTop
        const under = document.elementFromPoint(e.clientX, e.clientY)
        const row = under?.closest<HTMLElement>(".nav-item, .brain-row, button, a")
        if (row && container.contains(row)) {
          rail.classList.remove("tick")
          rail.style.left = ""
          rail.style.width = ""
          rail.style.top = row.offsetTop + "px"
          rail.style.height = row.offsetHeight + "px"
          rail.style.opacity = "1"
        } else {
          rail.classList.add("tick")
          rail.style.left = "10px"
          rail.style.width = "46px"
          rail.style.top = y - 1 + "px"
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
      aria-label="Jump to latest"
      title="Jump to latest"
    >
      <ArrowDown className="h-4 w-4" />
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

  useEffect(() => {
    const onScroll = () => {
      const focus = window.innerHeight * 0.35
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
      setActiveIdx(best)
    }
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  const userIndices = turns.reduce<number[]>((acc, t, i) => {
    if (t.role === "user") acc.push(i)
    return acc
  }, [])

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
          onClick={() => onJump(turnIdx)}
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

  useEffect(() => {
    if (!visible) return
    const w = window as unknown as {
      Clerk?: {
        openSignIn?: (props?: Record<string, unknown>) => void
        closeSignIn?: () => void
      }
    }
    if (!w.Clerk) return

    // Mirror the legacy auth.js appearance() — theme-matched Clerk component variables
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

    const props = {
      appearance: {
        variables,
        elements: {
          formButtonPrimary: "bg-accent text-accent-foreground hover:bg-accent/90",
          socialButtonsBlockButton: "border border-line bg-panel text-foreground hover:bg-wash-2",
          socialButtonsBlockButtonArrow: "text-muted-foreground",
          footerActionLink: "text-accent hover:text-accent-2",
        },
      },
      routing: "hash",
    } as Record<string, unknown>

    // Use openSignIn (modal) — this is the same method the legacy app uses for the
    // account modal and avoids React-managed-dom conflicts with mountSignIn
    w.Clerk.openSignIn?.(props)
  }, [visible])

  // Close Clerk modal when the gate hides
  useEffect(() => {
    if (!visible) {
      const w = window as unknown as { Clerk?: { closeSignIn?: () => void } }
      w.Clerk?.closeSignIn?.()
    }
  }, [visible])

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
        <div className="auth-title">Sign in to Kestrel</div>
        <div className="auth-sub">Your company's answers, grounded in your documents.</div>
        <div ref={mountRef} className="min-h-[300px]" />
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
  onClose: _onClose,
  onLanguage,
  onTheme,
  onUsage,
  onUpgrade,
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
  onAccount: () => void
  onSignOut: () => void
  signedIn: boolean
}) {
  if (!open) return null
  return (
    <div className="settings-pop" role="menu" aria-label="Settings">
      <button type="button" className="set-item" onClick={onLanguage} role="menuitem">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18z"/></svg>
        <span>Language</span>
        <svg className="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 6 6 6-6 6"/></svg>
      </button>
      <button type="button" className="set-item" onClick={onTheme} role="menuitem">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor" stroke="none"/></svg>
        <span>App theme</span>
        <svg className="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 6 6 6-6 6"/></svg>
      </button>
      <div className="set-sep" />
      <button type="button" className="set-item" onClick={onUsage} role="menuitem">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M4 20V10M10 20V4M16 20v-7M20 20H4"/></svg>
        <span>Usage stats</span>
      </button>
      <button type="button" className="set-item" onClick={onUpgrade} role="menuitem">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M5 15c-1.5 1.5-2 5-2 5s3.5-.5 5-2M14 4c3-2 7-1 7-1s1 4-1 7l-6 6-4-4 4-6z"/><circle cx="14.5" cy="9.5" r="1.4"/></svg>
        <span>Upgrade</span>
      </button>
      {signedIn && (
        <>
          <div className="set-sep" />
          <button type="button" className="set-item" onClick={onAccount} role="menuitem">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-3.5 4.5-5 8-5s6.5 1.5 8 5"/></svg>
            <span>Manage account</span>
          </button>
          <button type="button" className="set-item" onClick={onSignOut} role="menuitem">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 17l5-5-5-5M15 12H3"/></svg>
            <span>Disconnect</span>
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
