import { Suspense, lazy, useCallback, useEffect, useRef, useState, type FormEvent } from "react"
import { toast } from "sonner"
import { Sidebar, type SidebarUser } from "@/components/Sidebar"
import { Connectors } from "@/components/Connectors"
import { BrainsPage } from "@/components/BrainsPage"
import { SourceModal } from "@/components/SourceModal"
import { FilesSheet } from "@/components/FilesSheet"
import { DraftBox, type EmailDraftData } from "@/components/DraftBox"
import { CreateBrainDialog } from "@/components/CreateBrainDialog"
import { GraphView } from "@/components/GraphView"
import { LegacyMount } from "@/components/LegacyMount"
import { Toaster } from "@/components/ui/sonner"
import { PopMenu, AuthGate, SettingsMenu } from "@/components/Animations"
import {
  DEFAULT_BRAIN,
  greeting,
  useBrains,
  useChats,
  fetchChat,
  saveChat,
} from "@/lib/api"
import { t, fmt, setLang, getLang, getLangs, type LangCode } from "@/lib/i18n"
import { resolvedTheme, applyTheme, setTheme } from "@/theme"
import { loadClerk } from "@/lib/clerk"

const Markdown = lazy(() => import("@/components/Markdown"))

type Source = { source: string; excerpt?: string }
type Turn = { role: "user" | "bot"; text: string; sources?: Source[] }

// Same fields the legacy sidebar's userLabel() derives from the Clerk user
// (static/shell.js renderUser): display name, email, avatar initials.
function readClerkUser(): SidebarUser {
  const w = window as unknown as {
    Clerk?: {
      user?: {
        firstName?: string
        lastName?: string
        primaryEmailAddress?: string
        emailAddresses?: { emailAddress?: string }[]
        imageUrl?: string
      } | null
    }
  }
  const u = w.Clerk?.user
  if (!u) return null
  const nm = [u.firstName, u.lastName].filter(Boolean).join(" ")
  const em = u.primaryEmailAddress || (u.emailAddresses && u.emailAddresses[0] && u.emailAddresses[0].emailAddress) || ""
  const initials = ((u.firstName || "") + (u.lastName || "")).trim()
    ? (u.firstName || " ")[0] + (u.lastName || u.firstName || " ")[0]
    : (em || "K").slice(0, 2).toUpperCase()
  return { nm: nm || em || "Kestrel user", em, initials: initials.toUpperCase(), imageUrl: u.imageUrl }
}

// Legacy starter chips carry icons (static/index.html CHIP_ICON); the label
// sets below match STARTERS_DEMO / STARTERS_GENERIC.
const DEMO_CHIPS = [
  { icon: "doc", label: t("chip.demo1", "Why is the Bluepeak renewal at risk?"), query: "Why is the Bluepeak renewal at risk, and what have we promised them?" },
  { icon: "scale", label: t("chip.demo2", "What credit do we owe, and who approved it?"), query: "What service credit do we owe Bluepeak, and who approved it?" },
  { icon: "owner", label: t("chip.demo3", "Who owns the renewal and the RCA?"), query: "Who owns the Bluepeak renewal, and who owns the root cause analysis?" },
  { icon: "check", label: t("chip.demo4", "Is the renewal date consistent?"), query: "Is the Bluepeak renewal date consistent across our documents?" },
]
const GENERIC_CHIPS = [
  { icon: "doc", label: t("chip.gen1", "Summarise what is in this brain"), query: "Summarise what this brain knows — its main documents and topics." },
  { icon: "steps", label: t("chip.gen2", "What are the next steps?"), query: "What are the next steps across my documents, and who owns each one?" },
  { icon: "mail", label: t("chip.gen3", "Draft a mail from the latest answer"), query: "Draft a mail summarising the most recent answer." },
  { icon: "check", label: t("chip.gen4", "Is everything consistent?"), query: "Is everything in this brain consistent with each other?" },
]

// Legacy chip icon paths (static/index.html CHIP_ICON), verbatim.
const CHIP_ICON: Record<string, string> = {
  doc: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5",
  scale: "M12 3v18M5 7l7-4 7 4M3 13l2-6 2 6a2 2 0 0 1-4 0zM17 13l2-6 2 6a2 2 0 0 1-4 0z",
  owner: "M12 8m-3.5 0a3.5 3.5 0 1 0 7 0a3.5 3.5 0 1 0-7 0M5 20a7 7 0 0 1 14 0",
  check: "M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0-18 0M8.5 12l2.5 2.5 4.5-5",
  steps: "M4 6h16M4 12h10M4 18h13",
  mail: "M2.5 4.5h19v15h-19zM3 6l9 6.5L21 6",
}

function ChipSvg({ name }: { name: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d={CHIP_ICON[name] || CHIP_ICON.doc} />
    </svg>
  )
}

// Composer + message-action icon paths from static/index.html (BAR_ICON, ICON).
const SEND_D = "M12 19V5m0 0-6 6m6-6 6 6"
const STOP_D = "M6 6h12v12H6z" // filled rect in legacy; rendered with fill below
const PLUS_D = "M12 5v14M5 12h14"
const GRID_D = "M3 3h7.5v7.5H3zM13.5 3H21v7.5h-7.5zM3 13.5h7.5V21H3zM13.5 13.5H21V21h-7.5z"
const CHEV_DOWN_D = "m6 9 6 6 6-6"
const COPY_D = "M9 9h11v11H9zM5 15V5a2 2 0 0 1 2-2h10"
const UP_D = "M7 11v9M7 11l4-7c1.2 0 2 .9 2 2v4h5.2a1.8 1.8 0 0 1 1.8 2.1l-1 5.5A2 2 0 0 1 17 19H7"
const MAIL_ACT_D = "M2.5 4.5h19v15h-19zM3 6l9 6.5L21 6"
const DOWN_D = "M17 13V4M17 13l-4 7c-1.2 0-2-.9-2-2v-4H5.8a1.8 1.8 0 0 1-1.8-2.1l1-5.5A2 2 0 0 1 7 5h10"
const JUMP_D = "M12 5v14m0 0-6-6m6 6 6-6"
const DOC_D = CHIP_ICON.doc

// Mirrors the legacy shell's attachment contract: text-like files ride
// client-side, binary documents extract server-side, everything ingestible
// also lands in the current brain for FUTURE questions.
const TEXTY = /\.(txt|md|csv|json|py|js|ts|jsx|tsx|java|go|rs|c|cpp|h|hpp|sh|sql|yaml|yml|toml|ini|cfg|html|css)$/i
const CONTEXT_CAP = 6000

async function buildContext(files: File[], signal: AbortSignal | undefined): Promise<string> {
  let context = ""
  for (const f of files) {
    if (context.length >= 5200) break
    const texty = (f.type || "").startsWith("text/") || TEXTY.test(f.name)
    const imagey = (f.type || "").startsWith("image/")
    try {
      if (texty) {
        const content = (await f.slice(0, 16 * 1024).text()).slice(0, 2400)
        context = `Attached file "${f.name}":\n${content}\n\n${context}`
      } else if (!imagey) {
        const fd = new FormData()
        fd.append("file", f)
        const r = await fetch("/api/extract", { method: "POST", body: fd, signal })
        const d = await r.json()
        if (r.ok && d.text) {
          context = `Attached file "${f.name}":\n${String(d.text).slice(0, 2400)}\n\n${context}`
          if (d.ocr) toast.message(`${f.name} has no text layer — read via OCR`)
        } else {
          toast.warning(`Could not read ${f.name} — added to the brain only`)
        }
      }
    } catch (e) {
      if (signal?.aborted) throw e
      toast.warning(`Could not read ${f.name} — added to the brain only`)
    }
  }
  return context.slice(0, CONTEXT_CAP)
}

function cleanText(text: string): string {
  return (text || "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/^\s*[-*]\s+/gm, "• ")
    .replace(/^#{1,4}\s+/gm, "")
    .replace(/^[ \t]*\|[\s:|-]+\|[ \t]*$/gm, "")
    .replace(/^[ \t]*\|.*\|[ \t]*$/gm, (m) => m.replace(/\|/g, " ").replace(/\s+/g, " ").trim())
    .replace(/\n{3,}/g, "\n\n")
    .trim()
}

function transcript(turns: Turn[], format: "md" | "txt"): string {
  const lines = ["# Kestrel Company Brain — conversation", ""]
  turns.forEach((t) => {
    if (t.role === "user") {
      lines.push("## You", "", t.text, "")
      return
    }
    lines.push("## Kestrel", "", format === "txt" ? cleanText(t.text) : t.text, "")
    if (t.sources?.length) {
      const names = t.sources.filter((s) => s && s.source).map((s) => s.source)
      if (names.length) lines.push("Sources: " + names.join(", "), "")
    }
  })
  return lines.join("\n")
}

function downloadFile(name: string, body: string, mime: string) {
  const blob = new Blob([body], { type: (mime || "text/plain") + ";charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export default function App() {
  const [collapsed, setCollapsed] = useState(
    localStorage.getItem("kestrel.sb.collapsed") === "1",
  )
  const [mobileOpen, setMobileOpen] = useState(false)
  const [brain, setBrain] = useState(
    new URLSearchParams(location.search).get("brain") || DEFAULT_BRAIN,
  )
  const [turns, setTurns] = useState<Turn[]>([])
  const [streaming, setStreaming] = useState(false)
  const [input, setInput] = useState("")
  const [pendingFiles, setPendingFiles] = useState<File[]>([])
  const [sourcesPanel, setSourcesPanel] = useState<{ title: string; excerpt?: string } | null>(null)
  const [filesOpen, setFilesOpen] = useState(false)
  // P6 actions/draft surface: the email draft for the last answer
  const [draft, setDraft] = useState<EmailDraftData | null>(null)
  const [draftBusy, setDraftBusy] = useState(false)
  const chatIdRef = useRef<string | null>(null)
  const botIdxRef = useRef(-1)
  const turnsRef = useRef<Turn[]>([])
  useEffect(() => { turnsRef.current = turns }, [turns])
  const [greet, setGreet] = useState(greeting())
  const [chatId, setChatId] = useState<string | null>(
    new URLSearchParams(location.search).get("chat"),
  )
  useEffect(() => { chatIdRef.current = chatId }, [chatId])

  // Composer menus (legacy #menu2 / #brainmenu pops)
  const [menu2Open, setMenu2Open] = useState(false)
  const [brainMenuOpen, setBrainMenuOpen] = useState(false)
  const [clearArmed, setClearArmed] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const barCardRef = useRef<HTMLDivElement>(null)
  const formRef = useRef<HTMLFormElement>(null)

  // Animation / UI state
  const [restoring, setRestoring] = useState(false)
  const [switching, setSwitching] = useState(false)
  const [jumpVisible, setJumpVisible] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [langMenuOpen, setLangMenuOpen] = useState(false)
  const [themeMenuOpen, setThemeMenuOpen] = useState(false)
  const [workSteps, setWorkSteps] = useState<{ label: string; at: number; ms?: number }[]>([])
  const [workElapsed, setWorkElapsed] = useState(0)
  const [workOpen, setWorkOpen] = useState(true)
  const workStartRef = useRef(0)
  const workStoppedRef = useRef(0)
  const workTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [signedIn, setSignedIn] = useState(false)
  const [authMode, setAuthMode] = useState<string>("unknown")
  const [clerkUser, setClerkUser] = useState<SidebarUser>(null)

  // Message action feedback (legacy .msg-acts copied / fb-on marks)
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null)
  const [feedback, setFeedback] = useState<Record<number, "up" | "down" | undefined>>({})

  // Left rail (#rail): one tick per user turn; hover preview; scroll-linked
  const turnEls = useRef<Record<number, HTMLElement | null>>({})
  const [railHere, setRailHere] = useState<number | null>(null)
  const [railTip, setRailTip] = useState<{ x: number; y: number; label: string; answer: string } | null>(null)

  const [createOpen, setCreateOpen] = useState(false)
  const [view, setView] = useState<"chat" | "brains" | "connectors" | "graph" | "legacy-brains" | "legacy-upload" | "legacy-graph">(
    (() => {
      const v = new URLSearchParams(location.search).get("view")
      return v === "connectors" || v === "graph" || v === "brains" || v === "legacy-brains" || v === "legacy-upload" || v === "legacy-graph" ? v : "chat"
    })(),
  )

  // Deep-link restore (?chat=<id>) and reload resume: the legacy shell
  // remembers the open chat per brain in sessionStorage (static/index.html
  // CHAT_SESSION_KEY) and resumes it unless ?new=1 starts a fresh one.
  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const id = params.get("chat")
    if (id) {
      setRestoring(true)
      fetchChat(id)
        .then((serverTurns) => {
          if (serverTurns.length) setTurns(serverTurns)
        })
        .catch(() => {})
        .finally(() => setRestoring(false))
      return
    }
    if (params.get("new")) {
      try { sessionStorage.removeItem("kestrel.currentChat." + (brain || "demo")) } catch { /* private mode */ }
      return
    }
    let remembered: string | null = null
    try { remembered = sessionStorage.getItem("kestrel.currentChat." + (brain || "demo")) } catch { /* private mode */ }
    if (!remembered) return
    setRestoring(true)
    fetchChat(remembered)
      .then((serverTurns) => {
        if (!serverTurns.length) return
        setTurns(serverTurns)
        setChatId(remembered)
        const u = new URL(location.href)
        u.searchParams.set("chat", remembered)
        history.replaceState(null, "", u)
      })
      .catch(() => {})
      .finally(() => setRestoring(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Auth mode detection — mirrors legacy auth.js: fetch config, load Clerk,
  // await Clerk.load(), then check sessions for sign-in state
  useEffect(() => {
    let cancelled = false
    fetch("/api/config")
      .then((r) => r.json())
      .then((cfg) => {
        if (cancelled) return
        setAuthMode(cfg.authMode || "off")
        if (cfg.authMode === "clerk" && cfg.publishableKey) {
          loadClerk(cfg.publishableKey).then(() => {
            const w = window as unknown as {
              Clerk?: {
                session?: unknown
                client?: { sessions?: unknown[] }
                addListener?: (fn: () => void) => void
              }
            }
            const checkSignedIn = () => {
              if (cancelled) return
              const sessions = w.Clerk?.client?.sessions || []
              setSignedIn(!!w.Clerk?.session || sessions.length > 0)
              setClerkUser(readClerkUser())
            }
            checkSignedIn()
            w.Clerk?.addListener?.(checkSignedIn)
          })
        } else {
          setSignedIn(false)
        }
      })
      .catch(() => {
        if (!cancelled) setSignedIn(false)
      })
    return () => { cancelled = true }
  }, [])

  // Theme
  useEffect(() => {
    applyTheme()
  }, [])

  // i18n language event
  useEffect(() => {
    const onLang = () => setGreet(greeting())
    window.addEventListener("kestrel:lang", onLang)
    return () => window.removeEventListener("kestrel:lang", onLang)
  }, [])

  // The two-mode layout keys off BODY classes — the same classes the legacy
  // shell.js toggles (chatting / sb-collapsed / switching / locked / detached).
  const chatting = turns.length > 0 && view === "chat"
  useEffect(() => {
    const b = document.body
    b.classList.toggle("chatting", chatting)
    b.classList.toggle("sb-collapsed", collapsed)
    b.classList.toggle("switching", switching)
    b.classList.toggle("locked", authMode === "clerk" && !signedIn)
    b.classList.toggle("detached", chatting && jumpVisible)
    return () => {
      b.classList.remove("chatting", "sb-collapsed", "switching", "locked", "detached")
    }
  }, [chatting, collapsed, switching, authMode, signedIn, jumpVisible, view])

  // Scroll tracking: stick-to-bottom detection (#jump-latest via .detached)
  // and the #rail "you are here" tick (nearest user turn to the focus line).
  useEffect(() => {
    let raf = 0
    const onScroll = () => {
      if (raf) return
      raf = requestAnimationFrame(() => {
        raf = 0
        const stick = window.innerHeight + window.scrollY >= document.body.scrollHeight - 160
        setJumpVisible(!stick && turns.length > 0)
        const focus = window.innerHeight * 0.35
        let best: number | null = null
        let bestDist = Infinity
        for (const [idx, el] of Object.entries(turnEls.current)) {
          if (!el || turns[Number(idx)]?.role !== "user") continue
          const r = el.getBoundingClientRect()
          const dist = Math.abs(r.top + r.height / 2 - focus)
          if (dist < bestDist) { bestDist = dist; best = Number(idx) }
        }
        setRailHere(best)
      })
    }
    window.addEventListener("scroll", onScroll, { passive: true })
    onScroll()
    return () => { window.removeEventListener("scroll", onScroll); if (raf) cancelAnimationFrame(raf) }
  }, [turns])

  // Home must open at the top (legacy behaviour — focusing #q otherwise
  // scrolls the watermark above the fold).
  useEffect(() => { window.scrollTo(0, 0) }, [])

  // Escape closes the composer pops; a click outside .bar-anchor closes them.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setMenu2Open(false); setBrainMenuOpen(false); setClearArmed(false) }
    }
    const onClick = (e: MouseEvent) => {
      const inBar = (e.target as HTMLElement | null)?.closest?.(".bar-anchor")
      if (!inBar) { setMenu2Open(false); setBrainMenuOpen(false); setClearArmed(false) }
    }
    document.addEventListener("keydown", onKey)
    document.addEventListener("click", onClick)
    return () => { document.removeEventListener("keydown", onKey); document.removeEventListener("click", onClick) }
  }, [])

  const { chats, refreshChats } = useChats(view === "chat" ? brain : null)
  const { brains, refreshBrains } = useBrains()

  // Landing pad for the OAuth round-trip
  useEffect(() => {
    const u = new URLSearchParams(location.search)
    const connected = u.get("connected")
    const connectError = u.get("connect_error")
    if (connected) {
      setView("connectors")
      toast.success(`${connected[0].toUpperCase() + connected.slice(1)} connected`)
    } else if (connectError) {
      setView("connectors")
      toast.error(`Connection failed: ${decodeURIComponent(connectError)}`)
    }
    if (connected || connectError) {
      u.delete("connected")
      u.delete("connect_error")
      history.replaceState(null, "", `?${u.toString()}`.replace(/\?$/, ""))
    }
  }, [])

  useEffect(() => {
    const timer = setInterval(() => setGreet(greeting()), 60000)
    return () => clearInterval(timer)
  }, [])

  const scrollBottom = () => {
    window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" })
  }

  const startWork = () => {
    workStartRef.current = Date.now()
    workStoppedRef.current = 0
    setWorkElapsed(0)
    setWorkSteps([])
    setWorkOpen(true)
    if (workTimerRef.current) clearInterval(workTimerRef.current)
    workTimerRef.current = setInterval(() => {
      setWorkElapsed((Date.now() - workStartRef.current) / 1000)
    }, 100)
  }

  // Steps carry their start time so each done row can show its measured
  // duration ("✓ label · 0.5s"), exactly like the legacy workStart() log.
  // ms is the server-measured duration when the stream provides one.
  const addWorkStep = (label: string, ms?: number) => {
    setWorkSteps((prev) => [...prev, { label, at: Date.now(), ms }])
  }

  const stopWork = (stopped?: boolean) => {
    if (workTimerRef.current) {
      clearInterval(workTimerRef.current)
      workTimerRef.current = null
    }
    workStoppedRef.current = Date.now()
    if (stopped) {
      setWorkSteps((prev) => [...prev, { label: "stopped", at: Date.now() }])
    }
  }

  // Legacy saveHistory(): every finished ask is persisted server-side (and
  // the chat id remembered per brain for reload resume), not only failures.
  const persistChat = useCallback(() => {
    const id = chatIdRef.current || (chatIdRef.current = crypto.randomUUID())
    const firstUser = turnsRef.current.find((t) => t.role === "user")
    try {
      sessionStorage.setItem("kestrel.currentChat." + (brain || "demo"), id)
    } catch { /* private mode — id lives in the URL */ }
    return saveChat(id, firstUser ? firstUser.text.slice(0, 60) : "Untitled", brain, turnsRef.current.slice(-60))
      .then((ok) => ok && refreshChats())
      .catch(() => {})
  }, [brain, refreshChats])

  const ask = useCallback(async (q: string, files: File[] = []) => {
    // The bot turn opens immediately with the working log and the streaming
    // cursor (legacy addTurn('bot','') + workStart) — never only after the
    // first chunk arrives.
    setTurns((t) => {
      const botIdxLocal = t.length + 1
      botIdxRef.current = botIdxLocal
      return [...t, { role: "user", text: q }, { role: "bot", text: "" }]
    })
    setStreaming(true)
    startWork()
    const controller = new AbortController()
    ;(window as unknown as { CONTROLLER?: AbortController }).CONTROLLER = controller
    let text = ""
    try {
      const params = new URLSearchParams({ q })
      if (brain && brain !== "demo") params.set("dataset", brain)
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone
      params.set("tz", tz)
      params.set("local_time", new Date().toISOString())
      if (files.length) {
        addWorkStep("Reading attached files…")
        const context = await buildContext(files, controller.signal)
        if (context) params.set("context", context)
        const ingestible = files.filter((f) => !(f.type || "").startsWith("image/"))
        if (brain && brain !== "demo" && ingestible.length) {
          addWorkStep(`Adding ${ingestible.length} file(s) to ${brain}…`)
          const fd = new FormData()
          fd.append("name", brain)
          fd.append("append", "true")
          ingestible.forEach((f) => fd.append("files", f))
          fetch("/api/brains", { method: "POST", body: fd, signal: controller.signal })
            .then((r) => r.json())
            .then((d) => {
              if (d.ok || d.partial) toast.success(`Added to ${brain} — answerable in future questions`)
              else toast.warning(`Upload rejected: ${d.detail || "HTTP error"}`)
            })
            .catch(() => toast.warning("Upload failed: no response from server"))
        }
      }
      const res = await fetch(`/api/ask?${params}`, { signal: controller.signal })
      const reader = res.body!.getReader()
      const dec = new TextDecoder()
      let buf = ""
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const lines = buf.split("\n")
        buf = lines.pop() || ""
        for (const line of lines) {
          if (!line.trim()) continue
          const ev = JSON.parse(line)
          if (ev.type === "chunk") {
            text += ev.text || ""
            const idx = botIdxRef.current
            setTurns((t) => {
              const copy = [...t]
              // spread, not replace: references can land between chunks and
              // must survive the next text update
              if (copy[idx]) copy[idx] = { ...copy[idx], role: "bot", text }
              return copy
            })
            scrollBottom()
          } else if (ev.type === "references") {
            const items: Source[] = (ev.items || []).map((s: { source?: string; excerpt?: string }) => ({
              source: s.source || "source",
              excerpt: s.excerpt,
            }))
            setTurns((t) => {
              const copy = [...t]
              const idx = botIdxRef.current >= 0 ? botIdxRef.current : copy.length - 1
              if (copy[idx]?.role === "bot") copy[idx] = { ...copy[idx], sources: items }
              return copy
            })
          } else if (ev.stage === "error") {
            text += (text ? "\n\n" : "") + "⚠️ " + (ev.message || "The request failed.")
            const idx = botIdxRef.current
            setTurns((t) => {
              const copy = [...t]
              if (copy[idx]) copy[idx] = { ...copy[idx], role: "bot", text }
              return copy
            })
          } else if (ev.stage && ev.stage !== "done" && !ev.message) {
            const raw: string = ev.label || ev.stage
            // Same label mapping as legacy stageLabel(): the engine's raw
            // step names render as their friendly forms.
            const stageLabel =
              ev.stage === "start" ? t("stage.router_chat", "Searching the brain…") :
              ev.stage === "ready" ? t("stage.delegating", "Composing the answer…") :
              /^Smalltalk:/.test(raw) ? t("stage.smalltalk", raw) :
              /^Orchestrator: planning/.test(raw) ? t("stage.plan", raw) :
              /^Router: general chat/.test(raw) ? t("stage.router_chat", raw) :
              /^Delegating to/.test(raw) ? t("stage.delegating", raw) :
              raw
            addWorkStep(stageLabel, typeof ev.ms === "number" ? ev.ms : undefined)
          }
        }
      }
    } catch (e) {
      const err = e as Error
      if (err.name !== "AbortError") {
        const idx = botIdxRef.current
        setTurns((t) => {
          const copy = [...t]
          if (idx >= 0 && copy[idx]?.role === "bot" && !copy[idx].text) {
            copy[idx] = { role: "bot", text: "Could not reach the server: " + err.message }
            return copy
          }
          return [...t, { role: "bot", text: "Could not reach the server: " + err.message }]
        })
      }
    } finally {
      setStreaming(false)
      stopWork()
      scrollBottom()
      // The save itself runs in the streaming-flip effect below: it must see
      // the LAST chunk's commit, and turnsRef lags a render inside finally.
      justFinishedRef.current = true
    }
  }, [brain, persistChat])

  // Persist every finished ask (legacy saveHistory runs after finalize, not
  // only on failures). Runs post-commit so the saved turns include the final
  // streamed text.
  const justFinishedRef = useRef(false)
  useEffect(() => {
    if (streaming || !justFinishedRef.current) return
    justFinishedRef.current = false
    if (turnsRef.current.length) void persistChat()
  }, [streaming, persistChat])

  const handleSend = (q: string, files: File[] = []) => {
    if (!q.trim() && files.length === 0) return
    ask(q, files)
  }
  const handleStop = () => {
    ;(window as unknown as { CONTROLLER?: AbortController }).CONTROLLER?.abort()
    stopWork(true)
  }
  const openView = (v: "chat" | "brains" | "connectors" | "graph" | "legacy-brains" | "legacy-upload" | "legacy-graph") => {
    setView(v)
    const u = new URL(location.href)
    if (v === "chat") u.searchParams.delete("view")
    else u.searchParams.set("view", v)
    history.pushState(null, "", u)
  }
  const handleBrainChange = (b: string) => {
    if (b === "__upload__") { setCreateOpen(true); return }
    setChatId(null)
    openView("chat")
    setBrain(b)
    const u = new URL(location.href)
    u.searchParams.set("brain", b)
    history.pushState(null, "", u)
  }
  const openChat = async (id: string, chatBrain?: string) => {
    const target = chatBrain ?? brain
    setSwitching(true)
    handleBrainChange(target)
    const u = new URL(location.href)
    u.searchParams.set("chat", id)
    history.pushState(null, "", u)
    setChatId(id)
    const serverTurns = await fetchChat(id)
    if (serverTurns.length) setTurns(serverTurns)
    else setTurns([])
    setSwitching(false)
    setMobileOpen(false)
  }
  const newChat = () => {
    const u = new URL(location.href)
    u.searchParams.delete("chat")
    u.searchParams.set("new", "1")
    history.pushState(null, "", u)
    setChatId(null)
    setTurns([])
  }
  const toggleSidebar = () => {
    setCollapsed((c) => {
      localStorage.setItem("kestrel.sb.collapsed", c ? "0" : "1")
      return !c
    })
  }

  // Composer submit (form#f): send -> stop while streaming, same as legacy.
  const handleFormSubmit = (e?: FormEvent) => {
    e?.preventDefault()
    setMenu2Open(false)
    setBrainMenuOpen(false)
    if (streaming) {
      handleStop()
      return
    }
    const q = input.trim()
    if (q || pendingFiles.length) {
      handleSend(q, pendingFiles)
      setInput("")
      setPendingFiles([])
    }
  }

  const addFiles = (list: FileList | null) => {
    if (!list?.length) return
    setPendingFiles((cur) => [...cur, ...Array.from(list)].slice(0, 6))
  }

  // Composer textarea auto-grow (legacy: height auto -> min(scrollHeight,140))
  const qRef = useRef<HTMLTextAreaElement>(null)
  const growQ = () => {
    const el = qRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = Math.min(el.scrollHeight, 140) + "px"
  }

  // Clerk helpers
  const clerkSignOut = () => {
    const w = window as unknown as { Clerk?: { signOut?: () => Promise<void> } }
    w.Clerk?.signOut?.().catch(() => {})
  }
  const clerkOpenProfile = () => {
    const w = window as unknown as { Clerk?: { openUserProfile?: () => void } }
    w.Clerk?.openUserProfile?.()
  }

  // Theme helpers
  const currentTheme = resolvedTheme()

  // Language helpers
  const currentLang = getLang()
  const changeLang = (code: LangCode) => {
    setLang(code)
    setLangMenuOpen(false)
    setSettingsOpen(false)
  }

  // Export handlers (legacy #menu2 items)
  const handleExportMd = () => downloadFile("kestrel-conversation.md", transcript(turns, "md"), "text/markdown")
  const handleExportTxt = () => downloadFile("kestrel-conversation.txt", transcript(turns, "txt"), "text/plain")
  const handleExportDocx = () => {
    const md = transcript(turns, "md")
    const html = '<html xmlns:w="urn:schemas-microsoft-com:office:word"><head><meta charset="utf-8"><title>Kestrel conversation</title></head><body>' + md.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>") + "</body></html>"
    downloadFile("kestrel-conversation.doc", html, "application/msword")
  }
  const handleExportPdf = () => {
    const md = transcript(turns, "md")
    const frame = document.createElement("iframe")
    frame.setAttribute("aria-hidden", "true")
    frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;"
    document.body.appendChild(frame)
    const doc = frame.contentWindow!.document
    doc.open()
    doc.write('<!doctype html><meta charset="utf-8"><title>Kestrel conversation</title><style>body{font:12pt/1.6 -apple-system,Segoe UI,sans-serif;max-width:46em;margin:32px auto;padding:0 16px;color:#111}h1{font-size:20pt}h2{font-size:13pt;margin-top:20pt;color:#333}pre{white-space:pre-wrap;font-family:ui-monospace,Menlo,monospace;font-size:10pt;background:#f6f6f7;padding:12px;border-radius:6px}</style><h1>Kestrel Company Brain — conversation</h1><pre>' + md.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") + "</pre>")
    doc.close()
    setTimeout(() => {
      try {
        frame.contentWindow!.focus()
        frame.contentWindow!.print()
      } catch {}
      setTimeout(() => frame.remove(), 2000)
    }, 400)
  }
  const handleCopyTranscript = () => {
    navigator.clipboard.writeText(transcript(turns, "md")).catch(() => {})
    setMenu2Open(false)
  }

  // Legacy clear-chat: two-step armed confirm, then this chat is deleted
  // server-side and the thread resets to home.
  const handleClearChat = async () => {
    if (!clearArmed) { setClearArmed(true); return }
    setClearArmed(false)
    setMenu2Open(false)
    const id = chatId
    if (id) {
      try { await fetch(`/api/chats/${encodeURIComponent(id)}`, { method: "DELETE" }) } catch {}
    }
    newChat()
    refreshChats()
  }

  // Delete handlers
  const handleDeleteChat = async (targetId: string, _brain?: string) => {
    try {
      await fetch(`/api/chats/${encodeURIComponent(targetId)}`, { method: "DELETE" })
    } catch {}
    if (targetId === chatId) newChat()
    refreshChats()
  }
  const handleDeleteBrainChats = async (targetBrain: string) => {
    try {
      const r = await fetch(`/api/chats?brain=${encodeURIComponent(targetBrain)}`)
      const d = await r.json()
      for (const c of d.chats || []) {
        await fetch(`/api/chats/${encodeURIComponent(c.id)}`, { method: "DELETE" }).catch(() => {})
      }
    } catch {}
    if (targetBrain === brain) newChat()
    refreshChats()
  }

  // Message actions (legacy .msg-acts: copy with sources, quiet feedback marks)
  const copyAnswer = (i: number) => {
    const turn = turns[i]
    if (!turn) return
    const names = (turn.sources || []).map((s) => s.source).filter(Boolean)
    navigator.clipboard
      .writeText(cleanText(turn.text) + (names.length ? "\n\nSources: " + names.join(", ") : ""))
      .then(() => {
        setCopiedIdx(i)
        setTimeout(() => setCopiedIdx((cur) => (cur === i ? null : cur)), 1300)
      })
      .catch(() => {})
  }
  const markFeedback = (i: number, kind: "up" | "down") => {
    setFeedback((prev) => ({ ...prev, [i]: prev[i] === kind ? undefined : kind }))
  }

  // Draft a mail from an answer (POST /api/actions/draft — the agent only
  // drafts; sending is the explicit approval gate in the box).
  const draftFrom = async (i: number) => {
    if (draftBusy) return
    const turn = turns[i]
    if (!turn) return
    let question = ""
    for (let j = i - 1; j >= 0; j--) {
      if (turns[j].role === "user") { question = turns[j].text; break }
    }
    setDraftBusy(true)
    try {
      const r = await fetch("/api/actions/draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: "email",
          question,
          answer: turn.text,
          sources: (turn.sources || []).map((s) => s.source).filter(Boolean),
          brain,
        }),
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || !d.ok) {
        toast.error(d.detail || `HTTP ${r.status}`)
        return
      }
      setDraft({ to: d.draft?.to, subject: d.draft?.subject || "Kestrel answer", body: d.draft?.body || "" })
    } catch (e) {
      toast.error("Could not reach the server: " + (e as Error).message)
    } finally {
      setDraftBusy(false)
    }
  }

  const brainLabel = !brain || brain === "demo" || brain === DEFAULT_BRAIN ? "Demo brain" : brain
  // Legacy picks the generic starters only for a non-demo brain.
  const chips = brain && brain !== "demo" && brain !== DEFAULT_BRAIN ? GENERIC_CHIPS : DEMO_CHIPS
  const questionCount = turns.filter((turn) => turn.role === "user").length
  const goClass = streaming ? "stop" : ""
  const workDone = !streaming && workSteps.length > 0

  const renderTurn = (turn: Turn, i: number) => {
    if (turn.role === "user") {
      return (
        <div
          className="turn user"
          key={i}
          data-uid={i}
          ref={(el) => { turnEls.current[i] = el }}
        >
          <div className="bubble">{turn.text}</div>
        </div>
      )
    }
    const isLast = i === turns.length - 1
    const streamingHere = streaming && isLast
    const workingHere = isLast && workSteps.length > 0
    return (
      <div className="turn bot" key={i} data-uid={i} ref={(el) => { turnEls.current[i] = el }}>
        {workingHere && (
          <div className={"working" + (workDone && !workOpen ? " collapsed" : "")}>
            <div
              className={"working-head" + (workDone ? " toggle" : "")}
              title={workDone ? (workOpen ? "Hide the steps" : "Show the steps") : undefined}
              onClick={workDone ? () => setWorkOpen((o) => !o) : undefined}
            >
              {!workDone && <span className="spin" />}
              <span className="w-elapsed">{(workDone ? "Worked · " : "Working · ") + workElapsed.toFixed(1) + "s"}</span>
              {workSteps[workSteps.length - 1]?.label === "stopped" && <span className="w-stopped">· stopped</span>}
            </div>
            {workSteps.map((s, si) => {
              if (s.label === "stopped") return null
              const live = !workDone && si === workSteps.length - 1
              const endAt = workSteps[si + 1]?.at ?? (workDone ? workStoppedRef.current : Date.now())
              const dur = (s.ms != null ? (s.ms / 1000).toFixed(1) : ((endAt - s.at) / 1000).toFixed(1)) + "s"
              return (
                <div key={si} className={"w-step " + (live ? "live" : "done")}>
                  {live ? s.label : "✓ " + s.label + " · " + dur}
                </div>
              )
            })}
          </div>
        )}
        <div className={"bubble rendered" + (streamingHere ? " streaming" : "")}>
          {turn.text ? (
            <Suspense fallback={<span>{turn.text}</span>}>
              <Markdown>{turn.text}</Markdown>
            </Suspense>
          ) : null}
        </div>
        {turn.sources && turn.sources.length > 0 && (
          <div className="srcs">
            {turn.sources.map((s, si) => (
              <button
                type="button"
                key={si}
                title={t("src.open", "Open this source document")}
                onClick={() => setSourcesPanel({ title: s.source, excerpt: s.excerpt })}
              >
                {s.source}
              </button>
            ))}
          </div>
        )}
        {!streamingHere && (
          <div className="msg-acts">
            <button
              type="button"
              title="Copy this answer"
              aria-label="Copy this answer"
              className={copiedIdx === i ? "copied" : ""}
              onClick={() => copyAnswer(i)}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d={COPY_D} /></svg>
            </button>
            <button
              type="button"
              title="Draft a mail from this answer"
              aria-label="Draft a mail from this answer"
              onClick={() => void draftFrom(i)}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d={MAIL_ACT_D} /></svg>
            </button>
            <button
              type="button"
              title="Good answer"
              aria-label="Good answer"
              className={feedback[i] === "up" ? "fb-on" : ""}
              onClick={() => markFeedback(i, "up")}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d={UP_D} /></svg>
            </button>
            <button
              type="button"
              title="Needs work"
              aria-label="Needs work"
              className={feedback[i] === "down" ? "fb-on" : ""}
              onClick={() => markFeedback(i, "down")}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d={DOWN_D} /></svg>
            </button>
            <span className="time">{new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span>
          </div>
        )}
      </div>
    )
  }

  return (
    <>
      <a
        href="#kestrel-main"
        className="sr-only"
        onFocus={(e) => e.currentTarget.classList.remove("sr-only")}
        onBlur={(e) => e.currentTarget.classList.add("sr-only")}
      >
        Skip to chat
      </a>

      {/* Legacy .sb-toggle: re-opens a retracted bar; slides the off-canvas
          bar in on narrow screens */}
      <button
        type="button"
        className="sb-toggle"
        aria-label="Toggle navigation"
        onClick={() => {
          if (collapsed) toggleSidebar()
          else setMobileOpen((o) => !o)
        }}
      >
        ☰
      </button>

      <Sidebar
        mobileOpen={mobileOpen}
        onToggle={toggleSidebar}
        currentBrain={brain}
        currentChat={chatId}
        view={view}
        onViewChange={openView}
        onBrainChange={handleBrainChange}
        onNewChat={() => { newChat(); setMobileOpen(false) }}
        onOpenChat={(id, b) => void openChat(id, b ?? brain)}
        chats={chats}
        onRefreshChats={refreshChats}
        onDeleteChat={(id) => void handleDeleteChat(id)}
        onDeleteBrainChats={handleDeleteBrainChats}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenAccount={clerkOpenProfile}
        onSignOut={clerkSignOut}
        signedIn={signedIn}
        authMode={authMode}
        user={clerkUser}
      />

      <div className="app-main" id="kestrel-main">
        <h1 className="sr-only">Kestrel Company Brain</h1>
        {view === "connectors" ? (
          <Connectors />
        ) : view === "graph" ? (
          <GraphView brain={brain} />
        ) : view === "brains" ? (
          <BrainsPage />
        ) : view === "legacy-brains" ? (
          <LegacyMount path="/brains" label="Brains" />
        ) : view === "legacy-upload" ? (
          <LegacyMount path="/upload" label="Add documents" />
        ) : view === "legacy-graph" ? (
          <LegacyMount path="/graph" label="Graph (full)" />
        ) : (
          <>
            <div id="home">
              <div className="watermark">◆</div>
              <div className="greeting" id="greeting">{greet}</div>
            </div>
            <div id="thread-wrap">
              <div className="wrap">
                <div id="thread" aria-live="polite">
                  {turns.length === 0 && <div className="placeholder" id="empty" />}
                  {turns.map((turn, i) => renderTurn(turn, i))}
                </div>
                {draft && (
                  <DraftBox
                    draft={draft}
                    busy={draftBusy}
                    onBodyChange={(body) => setDraft((d) => (d ? { ...d, body } : d))}
                    onClose={() => setDraft(null)}
                  />
                )}
              </div>
            </div>
          </>
        )}
      </div>

      {view === "chat" && (
        <form id="f" ref={formRef} onSubmit={handleFormSubmit}>
          <div className="field">
            <div className="bar-card bar-anchor" ref={barCardRef}>
              <div className="bar-top">
                <button
                  type="button"
                  className="bar-btn"
                  id="brainswitch"
                  title={t("composer.switch_brain", "Switch brain")}
                  aria-label="Switch brain"
                  onClick={(e) => { e.stopPropagation(); setMenu2Open(false); setBrainMenuOpen((o) => !o) }}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d={GRID_D} /></svg>
                  <span className="bname" id="brainname">{brainLabel}</span>
                  <svg className="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d={CHEV_DOWN_D} /></svg>
                </button>
                <span className="spacer" />
                <button
                  type="button"
                  className="bar-btn"
                  id="menu2-toggle"
                  title={t("composer.actions", "Conversation actions")}
                  aria-label="Conversation actions"
                  onClick={(e) => { e.stopPropagation(); setBrainMenuOpen(false); setMenu2Open((o) => !o) }}
                >
                  ⋯
                </button>
              </div>

              {pendingFiles.length > 0 && (
                <div className="atts" id="pending">
                  {pendingFiles.map((f, i) => {
                    const imagey = (f.type || "").startsWith("image/")
                    return (
                      <div className="att" key={`${f.name}-${i}`}>
                        {imagey ? (
                          <img src={URL.createObjectURL(f)} alt={f.name} />
                        ) : (
                          <div className="att-file">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d={DOC_D} /></svg>
                            <span>{f.name}</span>
                          </div>
                        )}
                        <button
                          type="button"
                          className="x"
                          title="Remove attachment"
                          aria-label={`Remove ${f.name}`}
                          onClick={(e) => { e.stopPropagation(); setPendingFiles((cur) => cur.filter((_, j) => j !== i)) }}
                        >
                          ×
                        </button>
                      </div>
                    )
                  })}
                </div>
              )}

              <textarea
                id="q"
                ref={qRef}
                rows={1}
                value={input}
                onChange={(e) => { setInput(e.target.value); growQ() }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault()
                    formRef.current?.requestSubmit()
                  }
                }}
                placeholder={brain && brain !== "demo" && brain !== DEFAULT_BRAIN
                  ? t("composer.placeholder_brain", "Ask across the documents you uploaded…")
                  : t("composer.placeholder", "Ask across every document the company has written…")}
                autoComplete="off"
                autoFocus
              />

              <div className="bar-row">
                <button
                  type="button"
                  className="bar-btn"
                  id="attach"
                  title={t("composer.attach", "Attach files to this message")}
                  aria-label="Attach files to this message"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d={PLUS_D} /></svg>
                </button>
                <span className="spacer" style={{ flex: 1 }} />
                <button id="go" type="submit" className={goClass} aria-label={streaming ? "Stop generating" : "Send"}>
                  {streaming ? (
                    <svg viewBox="0 0 24 24" fill="currentColor"><path d={STOP_D} /></svg>
                  ) : (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d={SEND_D} /></svg>
                  )}
                </button>
              </div>

              <input
                ref={fileInputRef}
                type="file"
                id="chat-file"
                multiple
                hidden
                onChange={(e) => { addFiles(e.target.files); e.target.value = "" }}
              />

              <div className="pop" id="menu2" hidden={!menu2Open}>
                <div className="count">{fmt("menu.questions", { n: questionCount })}</div>
                <button type="button" id="copy-transcript" onClick={handleCopyTranscript}>{t("menu.copy_transcript", "Copy transcript")}</button>
                <button type="button" id="menu-addbrain" onClick={() => { setMenu2Open(false); setFilesOpen(true) }}>{t("menu.add_docs", "Add documents to this brain…")}</button>
                <div className="pop-sep" />
                <button type="button" id="export-md" onClick={() => { handleExportMd(); setMenu2Open(false) }}>{t("menu.export_md", "Export Markdown")}</button>
                <button type="button" id="export-txt" onClick={() => { handleExportTxt(); setMenu2Open(false) }}>{t("menu.export_txt", "Export plain text")}</button>
                <button type="button" id="export-docx" onClick={() => { handleExportDocx(); setMenu2Open(false) }}>{t("menu.export_docx", "Export Word document")}</button>
                <button type="button" id="export-pdf" onClick={() => { handleExportPdf(); setMenu2Open(false) }}>{t("menu.export_pdf", "Export PDF")}</button>
                <div className="pop-sep" />
                <button type="button" id="clear-chat" className={clearArmed ? "armed" : ""} onClick={handleClearChat}>
                  {clearArmed ? "Click again to clear" : t("menu.clear_chat", "Clear conversation")}
                </button>
              </div>

              <div className="pop" id="brainmenu" hidden={!brainMenuOpen}>
                <div className="pop-note">Ask in</div>
                {brains.map((b) => {
                  const isCurrent = b.name === brain
                  return (
                    <button
                      type="button"
                      key={b.name}
                      onClick={(e) => { e.stopPropagation(); if (!isCurrent) handleBrainChange(b.name); setBrainMenuOpen(false) }}
                    >
                      <span>{b.name}{b.is_demo ? " · demo" : ""}</span>
                      {isCurrent && <span className="tick">✓</span>}
                    </button>
                  )
                })}
                <div className="pop-sep" />
                <a
                  className="pop-item"
                  href="#"
                  onClick={(e) => { e.preventDefault(); setBrainMenuOpen(false); setCreateOpen(true) }}
                >
                  ＋ New brain…
                </a>
              </div>
            </div>
          </div>
        </form>
      )}

      {view === "chat" && (
        <div className="chips" id="chips">
          {chips.map((c) => (
            <button type="button" className="chip" key={c.label} onClick={() => handleSend(c.query)}>
              <ChipSvg name={c.icon} />
              <span>{c.label}</span>
            </button>
          ))}
        </div>
      )}

      <button
        type="button"
        id="jump-latest"
        title="Jump to latest"
        aria-label="Jump to latest"
        onClick={() => {
          scrollBottom()
          qRef.current?.focus()
        }}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d={JUMP_D} /></svg>
      </button>

      {/* Left rail — one tick per user turn; hover previews, click jumps */}
      <div id="rail">
        {turns.map((turn, i) =>
          turn.role !== "user" ? null : (
            <button
              type="button"
              key={i}
              className={"tick" + (railHere === i ? " here" : "")}
              style={{ animation: `railIn .3s ease ${i * 40}ms backwards` }}
              aria-label={`Jump to: ${(turn.text || "message").slice(0, 40)}`}
              onClick={() => turnEls.current[i]?.scrollIntoView({ behavior: "smooth", block: "center" })}
              onMouseEnter={(e) => {
                const answer = turns[i + 1] && turns[i + 1].role === "bot" ? cleanText(turns[i + 1].text).slice(0, 110) : ""
                const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
                setRailTip({ x: r.right + 12, y: Math.max(12, r.top - 14), label: (turn.text || "message").slice(0, 64), answer })
              }}
              onMouseLeave={() => setRailTip(null)}
            />
          ),
        )}
      </div>
      <div id="rail-tip" style={railTip ? { display: "block", left: railTip.x, top: railTip.y } : undefined}>
        {railTip && (
          <>
            <b>{railTip.label}</b>
            {railTip.answer ? railTip.answer + "…" : ""}
          </>
        )}
      </div>

      {sourcesPanel && (
        <SourceModal
          title={sourcesPanel.title}
          excerpt={sourcesPanel.excerpt}
          brain={brain}
          onClose={() => setSourcesPanel(null)}
        />
      )}

      {/* Legacy files sheet: add documents to the current brain */}
      <FilesSheet
        open={filesOpen}
        brain={brain && brain !== "demo" && brain !== DEFAULT_BRAIN ? brain : ""}
        onClose={() => setFilesOpen(false)}
        onAdded={refreshBrains}
      />

      {/* Legacy overlays: switch spinner + restore cover */}
      <div id="switch-fx" aria-hidden="true"><span className="spin big" /></div>
      <div id="restore" hidden={!restoring}>
        <div className="restore-card"><span className="spin" /> Restoring chat…</div>
      </div>

      {/* Auth gate */}
      <AuthGate visible={authMode === "clerk" && !signedIn} />

      {/* Settings menu */}
      <SettingsMenu
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onLanguage={() => { setSettingsOpen(false); setLangMenuOpen(true) }}
        onTheme={() => { setSettingsOpen(false); setThemeMenuOpen(true) }}
        onUsage={() => { setSettingsOpen(false); toast.info(t("usage.empty", "No model calls recorded yet.")) }}
        onUpgrade={() => { setSettingsOpen(false); toast.info(t("up.soon", "Coming soon")) }}
        onConnectors={() => { setSettingsOpen(false); openView("connectors") }}
        onAccount={clerkOpenProfile}
        onSignOut={clerkSignOut}
        signedIn={signedIn}
      />

      {/* Language sub-menu */}
      {langMenuOpen && (
        <PopMenu className="fixed bottom-16 left-3 z-[90] min-w-[190px] rounded-xl border border-line-2 bg-panel p-1.5 shadow-lg">
          <div className="px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground">
            {t("set.language", "Language")}
          </div>
          {getLangs().map((l) => (
            <button
              key={l.code}
              type="button"
              className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-[13px] text-fg-2 transition-colors hover:bg-wash hover:text-fg"
              onClick={() => changeLang(l.code)}
            >
              <span>{l.label}</span>
              {currentLang === l.code && <span className="ml-auto text-accent">✓</span>}
            </button>
          ))}
        </PopMenu>
      )}

      {/* Theme sub-menu */}
      {themeMenuOpen && (
        <PopMenu className="fixed bottom-16 left-3 z-[90] min-w-[190px] rounded-xl border border-line-2 bg-panel p-1.5 shadow-lg">
          <div className="px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground">
            {t("set.theme", "App theme")}
          </div>
          {(["system", "dark", "light"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-[13px] text-fg-2 transition-colors hover:bg-wash hover:text-fg"
              onClick={() => { setTheme(mode); setThemeMenuOpen(false) }}
            >
              <span>{t(`set.${mode}`, mode === "system" ? "System default" : mode === "dark" ? "Dark theme" : "Light theme")}</span>
              {currentTheme === mode && <span className="ml-auto text-accent">✓</span>}
            </button>
          ))}
        </PopMenu>
      )}

      <CreateBrainDialog
        open={createOpen}
        onClose={(created) => {
          setCreateOpen(false)
          refreshBrains()
          if (created) handleBrainChange(created)
        }}
      />

      <Toaster position="bottom-right" />
    </>
  )
}
