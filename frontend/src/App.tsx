import { Suspense, lazy, useCallback, useEffect, useRef, useState, type FormEvent } from "react"
import { toast } from "sonner"
import { Menu } from "lucide-react"
import { Sidebar, type SidebarUser } from "@/components/Sidebar"
import { Connectors } from "@/components/Connectors"
import { BrainsPage } from "@/components/BrainsPage"
import { SourceModal } from "@/components/SourceModal"
import { FilesSheet } from "@/components/FilesSheet"
import { DraftBox, type EmailDraftData } from "@/components/DraftBox"
import { CreateBrainDialog } from "@/components/CreateBrainDialog"
import { GraphView } from "@/components/GraphView"
import { Toaster } from "@/components/ui/sonner"
import { PopMenu, AuthGate, SettingsMenu, UsageModal, UpgradeModal } from "@/components/Animations"
import {
  DEFAULT_BRAIN,
  apiConfig,
  apiFetch,
  serverError,
  turnCap,
  useBrains,
  useChats,
  fetchChat,
  saveChat,
} from "@/lib/api"
import { t, fmt, setLang, getLang, getLangs, type LangCode } from "@/lib/i18n"
import { applyTheme, setTheme } from "@/theme"
import { loadClerk } from "@/lib/clerk"
import { CitationChip } from "@/components/CitationChip"

const Markdown = lazy(() => import("@/components/Markdown"))

type Source = { source: string; excerpt?: string; version?: string }
type Attachment = { name: string; kind: "image" | "file"; size: number; url?: string }
type WorkStep = { label: string; at: number; ms?: number }
type Turn = {
  role: "user" | "bot"
  text: string
  sources?: Source[]
  error?: boolean
  /** Legacy stores `at` with every turn (static/index.html:1142); restored
   *  messages used to render the CURRENT clock time instead. */
  at?: number
  /** Files that rode the message. Persisted so reopening a chat shows what the
   *  question was about (legacy:1245,1564-1590). */
  attachments?: Attachment[]
  /** The working log belongs to the TURN, not to the app: every answer keeps
   *  its own steps and measured durations (legacy workStart(turn)). */
  steps?: WorkStep[]
  workedMs?: number
  stopped?: boolean
}

// Same fields the legacy sidebar's userLabel() derives from the Clerk user
// (static/shell.js renderUser): display name, email, avatar initials.
// Every field is coerced to a string on purpose: newer Clerk builds return
// resource OBJECTS for email fields (an EmailAddress with verification/
// prepareVerification methods), and rendering one as JSX was React error #31
// — the whole app unmounted on sign-in. Only strings may cross this line.
function readClerkUser(): SidebarUser {
  const w = window as unknown as {
    Clerk?: {
      user?: {
        firstName?: unknown
        lastName?: unknown
        primaryEmailAddress?: unknown
        emailAddresses?: { emailAddress?: unknown }[]
        imageUrl?: unknown
      } | null
    }
  }
  const u = w.Clerk?.user
  if (!u) return null
  const str = (v: unknown): string => (typeof v === "string" ? v : "")
  const nm = [str(u.firstName), str(u.lastName)].filter(Boolean).join(" ")
  const em =
    str(u.primaryEmailAddress) ||
    (Array.isArray(u.emailAddresses) ? str(u.emailAddresses[0]?.emailAddress) : "")
  const initials = nm.trim()
    ? nm.trim()[0] + (str(u.lastName) || str(u.firstName) || " ")[0]
    : (em || "K").slice(0, 2).toUpperCase()
  return { nm: nm || em || "Kestrel user", em, initials: initials.toUpperCase(), imageUrl: str(u.imageUrl) }
}

// Legacy starter chips carry icons (static/index.html CHIP_ICON); the label
// sets below match STARTERS_DEMO / STARTERS_GENERIC.
// Chip labels are resolved at RENDER time, not import time: as module
// constants they were frozen in whatever language was active on first load, so
// switching language could never change them (the i18n no-op in §1.6 R2).
const DEMO_CHIPS = [
  { icon: "doc", labelKey: "chip.demo1", label: "Why is the Bluepeak renewal at risk?", query: "Why is the Bluepeak renewal at risk, and what have we promised them?" },
  { icon: "scale", labelKey: "chip.demo2", label: "What credit do we owe, and who approved it?", query: "What service credit do we owe Bluepeak, and who approved it?" },
  { icon: "owner", labelKey: "chip.demo3", label: "Who owns the renewal and the RCA?", query: "Who owns the Bluepeak renewal, and who owns the root cause analysis?" },
  { icon: "check", labelKey: "chip.demo4", label: "Is the renewal date consistent?", query: "Is the Bluepeak renewal date consistent across our documents?" },
]
const GENERIC_CHIPS = [
  { icon: "doc", labelKey: "chip.gen1", label: "Summarise what is in this brain", query: "Summarise what this brain knows — its main documents and topics." },
  { icon: "steps", labelKey: "chip.gen2", label: "What are the next steps?", query: "What are the next steps across my documents, and who owns each one?" },
  { icon: "mail", labelKey: "chip.gen3", label: "Draft a mail from the latest answer", query: "Draft a mail summarising the most recent answer." },
  { icon: "check", labelKey: "chip.gen4", label: "Is everything consistent?", query: "Is everything in this brain consistent with each other?" },
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
        const r = await apiFetch("/api/extract", { method: "POST", body: fd, signal })
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

// Same label mapping as legacy stageLabel() (static/index.html:602): the
// engine's raw step names render as their friendly forms. Only `stage:"step"`
// events carry a label — matching every stage is what made the first row of
// every ask read "General chat — bypassing retrieval" (the `stage:"start"`
// event has no label and picked up the router string).
function stageLabel(raw: string): string {
  if (/^Smalltalk:/.test(raw)) return t("stage.smalltalk", raw)
  if (/^Orchestrator: planning/.test(raw)) return t("stage.plan", raw)
  if (/^Router: general chat/.test(raw)) return t("stage.router_chat", raw)
  if (/^Delegating to/.test(raw)) return t("stage.delegating", raw)
  return raw
}

// Attachments ride the message (legacy:1245,1523-1532). Files over 8 MB are
// refused — the old React path accepted anything and read a 200 MB file into
// memory; files under 1.5 MB are snapshotted as data URLs so reopening the chat
// still shows what the question was about.
const MAX_ATTACH_BYTES = 8 * 1024 * 1024
const ATTACH_SNAPSHOT_BYTES = 1.5 * 1024 * 1024

async function buildAttachments(files: File[]): Promise<Attachment[]> {
  const out: Attachment[] = []
  for (const f of files) {
    const kind: Attachment["kind"] = (f.type || "").startsWith("image/") ? "image" : "file"
    let url: string | undefined
    if (f.size <= ATTACH_SNAPSHOT_BYTES) {
      url = await new Promise<string>((resolve) => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result || ""))
        reader.onerror = () => resolve("")
        reader.readAsDataURL(f)
      })
      if (!url) url = undefined
    }
    out.push({ name: f.name, kind, size: f.size, url })
  }
  return out
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

/**
 * Copy text, with the legacy fallback.
 *
 * navigator.clipboard is undefined on plain http (a LAN host, a container IP),
 * where the old code silently did nothing — no error, no copy. Legacy kept a
 * hidden textarea + execCommand path for exactly that (index.html:1887-1900).
 */
async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch { /* fall through to the legacy path */ }
  try {
    const ta = document.createElement("textarea")
    ta.value = text
    ta.setAttribute("readonly", "")
    ta.style.cssText = "position:fixed;top:-1000px;left:-1000px;opacity:0;"
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand("copy")
    ta.remove()
    return ok
  } catch {
    return false
  }
}

function newChatId(): string {
  const c = globalThis.crypto as Crypto | undefined
  if (c && typeof c.randomUUID === "function") return c.randomUUID()
  return "c" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
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

/**
 * Blob URLs for the composer's pending images, created once per file list and
 * revoked when that list changes.
 *
 * The old code called URL.createObjectURL(f) inline in the render. The composer
 * re-renders on every keystroke, so ten seconds of typing next to one attached
 * screenshot left a hundred-plus live blob URLs retained until unload — a leak
 * whose whole cost is invisible in the DOM. downloadFile above already pairs each
 * createObjectURL with a revoke; this is the same discipline on the path that
 * renders continuously.
 */
function useObjectUrls(files: File[]) {
  const [urls, setUrls] = useState<string[]>([])
  useEffect(() => {
    const created = files.map(f => URL.createObjectURL(f))
    setUrls(created)
    return () => { created.forEach(u => URL.revokeObjectURL(u)) }
  }, [files])
  return urls
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
  const [sourcesPanel, setSourcesPanel] = useState<{ title: string; excerpt?: string; version?: string } | null>(null)

  // Stable object URLs for the previews above.
  const attachmentPreviews = useObjectUrls(pendingFiles)
  const [filesOpen, setFilesOpen] = useState(false)
  // P6 actions/draft surface: the email draft for the last answer
  const [draft, setDraft] = useState<EmailDraftData | null>(null)
  const [draftBusy, setDraftBusy] = useState(false)
  const chatIdRef = useRef<string | null>(null)
  const botIdxRef = useRef(-1)
  const turnsRef = useRef<Turn[]>([])
  useEffect(() => { turnsRef.current = turns }, [turns])
  // Language is React state so a switch repaints the whole shell; the module
  // variable alone only changed strings that happened to re-render.
  const [lang, setLangState] = useState<LangCode>(getLang())
  const greetFor = () => {
    const h = new Date().getHours()
    return h < 12 ? t("greet.morning", "Morning, how can I help?")
      : h < 17 ? t("greet.afternoon", "Afternoon, how can I help?")
      : t("greet.evening", "Evening, how can I help?")
  }
  const [greet, setGreet] = useState(greetFor)
  const [chatId, setChatId] = useState<string | null>(
    new URLSearchParams(location.search).get("chat"),
  )
  useEffect(() => { chatIdRef.current = chatId }, [chatId])

  // Composer menus (legacy #menu2 / #brainmenu pops)
  const [menu2Open, setMenu2Open] = useState(false)
  const [brainMenuOpen, setBrainMenuOpen] = useState(false)
  // Switching brains mid-conversation starts a fresh chat (legacy asks twice:
  // "Switch and start a fresh chat?" — index.html:731-737).
  const [brainSwitchArmed, setBrainSwitchArmed] = useState<string | null>(null)
  const [clearArmed, setClearArmed] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const barCardRef = useRef<HTMLDivElement>(null)
  const formRef = useRef<HTMLFormElement>(null)

  // Animation / UI state
  const [restoring, setRestoring] = useState(false)
  const [switching, setSwitching] = useState(false)
  const [jumpVisible, setJumpVisible] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [usageOpen, setUsageOpen] = useState(false)
  const [upgradeOpen, setUpgradeOpen] = useState(false)
  // Where the language/theme submenu sits: legacy anchors a .sub-pop to the
  // right of the settings item it came from (shell.js subMenu), falling back to
  // the left edge when there is no room.
  const [subMenuPos, setSubMenuPos] = useState<{ left: number; bottom: number } | null>(null)
  const [langMenuOpen, setLangMenuOpen] = useState(false)
  const [themeMenuOpen, setThemeMenuOpen] = useState(false)
  const [workElapsed, setWorkElapsed] = useState(0)
  const workStartRef = useRef(0)
  const workTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // Completed logs collapse into their header (legacy .working.collapsed);
  // clicking one expands it. Keyed by turn index.
  const [expandedLogs, setExpandedLogs] = useState<Record<number, boolean>>({})
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
  const [view, setView] = useState<"chat" | "brains" | "connectors" | "graph">(
    (() => {
      const v = new URLSearchParams(location.search).get("view")
      return v === "connectors" || v === "graph" || v === "brains" ? v : "chat"
    })(),
  )

  // Legacy restoreHistory() prefix rescue (static/index.html:977-1000): a
  // truncated or stale ?chat= id (seen in the wild as 12 of 13 characters)
  // resolves to nothing and blanked the thread. Find the unique chat the id was
  // meant to be, restore it, and correct the URL.
  const rescueByPrefix = async (id: string): Promise<string | null> => {
    if (id.length < 8) return null
    try {
      const r = await apiFetch("/api/chats?limit=500")
      if (!r.ok) return null
      const d = await r.json()
      const hits = (d.chats || []).filter((c: { id: string }) => c.id.startsWith(id))
      return hits.length === 1 ? hits[0].id : null
    } catch {
      return null
    }
  }

  // Deep-link restore (?chat=<id>) and reload resume: the legacy shell
  // remembers the open chat per brain in sessionStorage (static/index.html
  // CHAT_SESSION_KEY) and resumes it unless ?new=1 starts a fresh one.
  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const id = params.get("chat")
    if (id) {
      setRestoring(true)
      const load = async (wanted: string) => {
        try {
          const serverTurns = await fetchChat(wanted)
          setTurns(serverTurns)
          return true
        } catch (e) {
          const better = await rescueByPrefix(wanted)
          if (better) {
            const turns2 = await fetchChat(better)
            setTurns(turns2)
            setChatId(better)
            const u = new URL(location.href)
            u.searchParams.set("chat", better)
            history.replaceState(null, "", u)
            return true
          }
          // A restore that fails must say so: silently showing an empty thread
          // is indistinguishable from a chat that was never saved.
          toast.error("Could not restore this chat: " + (e as Error).message)
          return false
        }
      }
      load(id).finally(() => setRestoring(false))
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
    ;(async () => {
      try {
        const serverTurns = await fetchChat(remembered)
        setTurns(serverTurns)
        setChatId(remembered)
        const u = new URL(location.href)
        u.searchParams.set("chat", remembered)
        history.replaceState(null, "", u)
      } catch (e) {
        // The remembered id is gone (deleted here or in another tab): stop
        // remembering it rather than failing on every load.
        try { sessionStorage.removeItem("kestrel.currentChat." + (brain || "demo")) } catch { /* private mode */ }
        toast.error("Could not resume this chat: " + (e as Error).message)
      } finally {
        setRestoring(false)
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Auth mode detection — mirrors legacy auth.js: fetch config, load Clerk,
  // await Clerk.load(), then check sessions for sign-in state. The config is
  // shared with the transport (lib/api.ts apiConfig) so there is one fetch.
  useEffect(() => {
    let cancelled = false
    apiConfig()
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

  // i18n language event: any setLang (ours or another surface's) repaints.
  useEffect(() => {
    const onLang = () => {
      setLangState(getLang())
      setGreet(greetFor())
    }
    window.addEventListener("kestrel:lang", onLang)
    return () => window.removeEventListener("kestrel:lang", onLang)
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
        stickRef.current = stick
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

  // Back/Forward re-derives the view from the URL. Every navigation in this app
  // is a pushState, so without this the address bar described something the
  // screen was not showing (legacy was a page load per nav, so it never had to).
  useEffect(() => {
    const onPop = () => {
      const p = new URLSearchParams(location.search)
      const v = p.get("view")
      setView(
        v === "connectors" || v === "graph" || v === "brains" ? v : "chat",
      )
      setBrain(p.get("brain") || DEFAULT_BRAIN)
      const id = p.get("chat")
      setChatId(id)
      if (!id) { setTurns([]); return }
      setRestoring(true)
      fetchChat(id)
        .then((serverTurns) => setTurns(serverTurns))
        .catch((e) => toast.error("Could not restore this chat: " + (e as Error).message))
        .finally(() => setRestoring(false))
    }
    window.addEventListener("popstate", onPop)
    return () => window.removeEventListener("popstate", onPop)
  }, [])

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

  useEffect(() => {
    document.title = brainLabel + " — Kestrel"
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brain])

  // CH-12: in clerk mode there is nothing to read before there is a session.
  // Firing anyway put two 401s in the console on every signed-out load — the
  // server was right to refuse, the client was wrong to ask. "unknown" must NOT
  // count as "not clerk": the mode is decided by /api/config a tick later, and
  // treating not-yet-known as off is what made the first attempt fetch anyway.
  const canRead = authMode !== "unknown" && (authMode !== "clerk" || signedIn)
  const { chats, refreshChats, chatsError, total: chatsTotal,
          truncated: chatsTruncated } = useChats(canRead)
  const { brains, refreshBrains, brainsError } = useBrains(canRead)

  // Landing pad for the OAuth round-trip
  useEffect(() => {
    const u = new URLSearchParams(location.search)
    const connected = u.get("connected")
    const connectError = u.get("connect_error")
    if (connected || connectError) {
      // Strip the round-trip params FIRST, then navigate: openView builds the new URL
      // off location.href, and doing it the other way round re-wrote the cleaned URL
      // with a stale copy that dropped `view` again.
      u.delete("connected")
      u.delete("connect_error")
      // An empty string is NOT a URL to history.replaceState — it means "leave the
      // address alone" — and when the round-trip param was the only one on the way
      // back, `?` + "" reduced to exactly that. The cleanup was a no-op in the common
      // case: /?connected=google stayed in the address bar after the landing pad ran.
      const query = u.toString()
      history.replaceState(null, "", location.pathname + (query ? `?${query}` : ""))
      // openView is the only thing that keeps `view` state and the address in the same
      // sentence. This used to call setView directly, which showed Connectors while the
      // URL still said chat — so a reload, a bookmark or a back press landed the user
      // somewhere they were not looking at, with a toast already gone.
      openView("connectors")
      if (connected) {
        toast.success(`${connected[0].toUpperCase() + connected.slice(1)} connected`)
      } else {
        toast.error(`Connection failed: ${decodeURIComponent(connectError || "")}`)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const timer = setInterval(() => setGreet(greetFor()), 60000)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Legacy honours `stick`: scrolling up to read an answer in progress must not
  // be undone by the next token. Streaming scrolls are instant (smooth scrolling
  // per chunk jitters and fights the reader).
  const stickRef = useRef(true)
  const scrollBottom = (instant = false) => {
    window.scrollTo({ top: document.body.scrollHeight, behavior: instant ? "auto" : "smooth" })
  }
  const scrollIfStuck = () => {
    if (stickRef.current) scrollBottom(true)
  }

  const patchTurn = useCallback((idx: number, patch: Partial<Turn>) => {
    setTurns((t) => {
      const copy = [...t]
      if (copy[idx]) copy[idx] = { ...copy[idx], ...patch }
      return copy
    })
  }, [])

  const startWork = useCallback((idx: number) => {
    workStartRef.current = Date.now()
    setWorkElapsed(0)
    patchTurn(idx, { steps: [], workedMs: 0, stopped: false })
    setExpandedLogs((prev) => ({ ...prev, [idx]: true }))
    if (workTimerRef.current) clearInterval(workTimerRef.current)
    workTimerRef.current = setInterval(() => {
      setWorkElapsed((Date.now() - workStartRef.current) / 1000)
    }, 100)
  }, [patchTurn])

  // Steps carry their start time so each done row can show its measured
  // duration ("✓ label · 0.5s"), exactly like the legacy workStart() log.
  // ms is the server-measured duration when the stream provides one.
  const addWorkStep = useCallback((idx: number, label: string, ms?: number) => {
    setTurns((t) => {
      const copy = [...t]
      const turn = copy[idx]
      if (turn) copy[idx] = { ...turn, steps: [...(turn.steps || []), { label, at: Date.now(), ms }] }
      return copy
    })
  }, [])

  const stopWork = useCallback((idx: number, stopped?: boolean) => {
    if (workTimerRef.current) {
      clearInterval(workTimerRef.current)
      workTimerRef.current = null
    }
    const workedMs = workStartRef.current ? Date.now() - workStartRef.current : 0
    setTurns((t) => {
      const copy = [...t]
      const turn = copy[idx]
      if (turn) {
        copy[idx] = {
          ...turn,
          workedMs,
          stopped: !!stopped,
          steps: stopped
            ? [...(turn.steps || []), { label: "stopped", at: Date.now() }]
            : turn.steps,
        }
      }
      return copy
    })
    setExpandedLogs((prev) => ({ ...prev, [idx]: false }))
  }, [])

  // Legacy saveHistory(): every finished ask is persisted server-side (and
  // the chat id remembered per brain for reload resume), not only failures.
  const persistChat = useCallback(() => {
    // crypto.randomUUID throws outside a secure context (plain http on a LAN
    // host); the legacy shell used a timestamp id and always worked.
    const id = chatIdRef.current || (chatIdRef.current = newChatId())
    const firstUser = turnsRef.current.find((t) => t.role === "user")
    try {
      sessionStorage.setItem("kestrel.currentChat." + (brain || "demo"), id)
    } catch { /* private mode — id lives in the URL */ }
    // Legacy rememberChat(): clear ?new and point ?chat at this conversation.
    // Without it, reloading after a fresh ask re-ran the "start a new chat"
    // branch and showed an empty thread beside a saved, listed chat.
    if (location.search.includes("new=") || !location.search.includes("chat=")) {
      const u = new URL(location.href)
      u.searchParams.set("chat", id)
      u.searchParams.delete("new")
      history.replaceState(null, "", u)
      setChatId(id)
    }
    const title = firstUser ? firstUser.text.slice(0, 60) : "Untitled"
    // CH-1: the WHOLE conversation is sent. `slice(-60)` was silent, permanent
    // data loss — the server rewrites the turn set, so the 61st message deleted
    // turns 1..N with no error and no trace anywhere. Trimming is now the
    // exception (only past the cap the SERVER publishes) and it is declared, so
    // a deliberate trim can be told apart from a stale window.
    return turnCap().then((cap) => {
      const all = turnsRef.current
      const trimmed = all.length > cap
      const keep = trimmed ? all.slice(all.length - cap) : all
      const send = (chatId: string) =>
        saveChat(chatId, title, brain, keep, trimmed).then((r) => ({ chatId, r }))
      return send(id).then(({ r }) => {
        if (r.ok) {
          if (trimmed) toast.warning(`Only the newest ${cap} turns of a chat are kept.`)
          refreshChats()
          return true
        }
        if (r.status === 410) {
          // CH-2: this chat was deleted — here, in another tab, on another
          // device. Never re-create it. But the reader is still looking at a
          // real conversation, so it moves to a fresh id instead of vanishing.
          const fresh = newChatId()
          chatIdRef.current = fresh
          setChatId(fresh)
          const u = new URL(location.href)
          u.searchParams.set("chat", fresh)
          u.searchParams.delete("new")
          history.replaceState(null, "", u)
          try { sessionStorage.setItem("kestrel.currentChat." + (brain || "demo"), fresh) } catch { /* private mode */ }
          toast.warning("That chat had been deleted — saved as a new chat.")
          return send(fresh).then(({ r: r2 }) => {
            if (!r2.ok) toast.error(`Could not save this chat (HTTP ${r2.status}).`)
            else refreshChats()
            return r2.ok
          })
        }
        if (r.status === 409) {
          // Another tab saved a longer version of this chat first. Overwriting
          // it with this window would delete its turns, so this one stops and
          // re-reads the list instead.
          toast.error("Another tab changed this chat first — not overwriting it.")
          refreshChats()
          return false
        }
        toast.error(`Could not save this chat (HTTP ${r.status}).`)
        return false
      })
    }).catch((e) => {
      // The old handler was `.catch(() => {})`: a failed save was invisible, and
      // the chat simply was not there on the next load.
      toast.error("Could not save this chat: " + (e as Error).message)
      return false
    })
  }, [brain, refreshChats])

  const finalizedRef = useRef(false)
  const [saveTick, setSaveTick] = useState(0)

  const ask = useCallback(async (q: string, files: File[] = []) => {
    // The bot turn opens immediately with the working log and the streaming
    // cursor (legacy addTurn('bot','') + workStart) — never only after the
    // first chunk arrives.
    // Index the bot turn BEFORE any await, from the same snapshot the reducer
    // uses, so every write lands on this ask's turn even if another starts.
    const botIdx = turnsRef.current.length + 1
    botIdxRef.current = botIdx
    const now = Date.now()
    const attachments = await buildAttachments(files)
    setTurns((t) => [
      ...t,
      { role: "user", text: q, at: now, attachments: attachments.length ? attachments : undefined },
      { role: "bot", text: "", at: now, steps: [] },
    ])
    setStreaming(true)
    finalizedRef.current = false
    // A new question is an intent to follow the answer: re-stick.
    stickRef.current = true
    startWork(botIdx)
    scrollBottom(true)
    const controller = new AbortController()
    ;(window as unknown as { CONTROLLER?: AbortController }).CONTROLLER = controller
    let text = ""
    let serverError: string | null = null
    let aborted = false

    // Write to the bot turn this ask opened (botIdxRef), never to "the last
    // turn" — the index is captured before any await.
    const setBotText = (value: string, extra?: Partial<Turn>) => {
      const idx = botIdxRef.current
      setTurns((t) => {
        const copy = [...t]
        if (idx >= 0 && copy[idx]?.role === "bot") {
          copy[idx] = { ...copy[idx], role: "bot", text: value, ...extra }
        }
        return copy
      })
    }

    // Legacy finalize(): the composer is freed the moment the answer is
    // complete. Citations keep arriving afterwards into the finished turn, so
    // this must not end the read loop (static/index.html:1256-1281,1408-1417).
    const finalize = () => {
      if (finalizedRef.current) return
      finalizedRef.current = true
      setStreaming(false)
      stopWork(botIdx)
    }

    try {
      const params = new URLSearchParams({ q })
      if (brain && brain !== "demo") params.set("dataset", brain)
      params.set("tz", Intl.DateTimeFormat().resolvedOptions().timeZone)
      params.set("local_time", new Date().toISOString())
      // Which language to answer a greeting in. Locale only: it never chooses what is
      // retrieved, so a question stays answered from the documents in the language it
      // was asked in. Sent because the phatic replies live server-side now, and a
      // German UI getting an English "Good morning" is a visible inconsistency.
      params.set("lang", getLang())

      // A follow-up is resolved against the last few turns: without this every
      // question is a cold start and "and who signs it off?" has no referent
      // (static/index.html:1237-1239 → app.py:1164-1194).
      let context = turnsRef.current
        .slice(-3)
        .map((t) => (t.role === "user" ? "Earlier question: " : "Earlier answer: ") + (t.text || "").slice(0, 700))
        .join("\n")
        .trim()

      if (files.length) {
        addWorkStep(botIdx, "Reading attached files…")
        const fileContext = await buildContext(files, controller.signal)
        if (fileContext) context = fileContext + (context ? "\n\n" + context : "")
        const ingestible = files.filter((f) => !(f.type || "").startsWith("image/"))
        if (brain && brain !== "demo" && ingestible.length) {
          addWorkStep(botIdx, `Adding ${ingestible.length} file(s) to ${brain}…`)
          const fd = new FormData()
          fd.append("name", brain)
          fd.append("append", "true")
          ingestible.forEach((f) => fd.append("files", f))
          apiFetch("/api/brains", { method: "POST", body: fd, signal: controller.signal })
            .then((r) => r.json())
            .then((d) => {
              if (d.ok || d.partial) toast.success(`Added to ${brain} — answerable in future questions`)
              else toast.warning(`Upload rejected: ${d.detail || "HTTP error"}`)
            })
            .catch(() => toast.warning("Upload failed: no response from server"))
        }
      }
      if (context) params.set("context", context.slice(0, CONTEXT_CAP))

      const res = await apiFetch(`/api/ask?${params}`, { signal: controller.signal })
      // A 401/500 answers with a JSON body and no trailing newline. Without
      // this guard the buffer-tail logic swallowed it and the user got a
      // permanently empty answer with no error at all.
      if (!res.ok || !res.body) {
        const detail = await res.json().catch(() => null)
        throw new Error((detail && detail.detail) || `HTTP ${res.status}`)
      }
      const reader = res.body.getReader()
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
          let ev: {
            type?: string; text?: string; stage?: string; label?: string
            message?: string; ms?: number
            items?: { source?: string; excerpt?: string; document_version_id?: string }[]
          }
          // One malformed line must never kill the stream (legacy:1398).
          try { ev = JSON.parse(line) } catch { continue }
          if (ev.type === "chunk") {
            text += ev.text || ""
            setBotText(text)
            scrollIfStuck()
          } else if (ev.type === "references") {
            const items: Source[] = (ev.items || [])
              .filter((s) => s && s.source)
              .map((s) => ({ source: s.source as string, excerpt: s.excerpt,
                             version: s.document_version_id }))
            const idx = botIdxRef.current >= 0 ? botIdxRef.current : turnsRef.current.length - 1
            setTurns((t) => {
              const copy = [...t]
              if (copy[idx]?.role === "bot") copy[idx] = { ...copy[idx], sources: items }
              return copy
            })
            // References land AFTER done: the turn is already saved without
            // them, so save again or the chips vanish on reload (legacy:1410).
            if (finalizedRef.current) {
              justFinishedRef.current = true
              setSaveTick((n) => n + 1)
            }
          } else if (ev.stage === "step") {
            addWorkStep(botIdx, stageLabel(ev.label || ""), typeof ev.ms === "number" ? ev.ms : undefined)
          } else if (ev.stage === "done") {
            finalize()
          } else if (ev.stage === "error") {
            serverError = ev.message || "The request failed."
          }
        }
      }
      if (serverError && !text) {
        setBotText("Something went wrong: " + serverError, { error: true })
      } else if (serverError) {
        // Keep the partial answer that did arrive, and say what happened.
        setBotText(text)
        toast.error(serverError)
      } else if (!text) {
        setBotText("No answer returned for that question.")
      }
    } catch (e) {
      const err = e as Error
      if (err.name === "AbortError") {
        aborted = true
        setBotText(text ? text + "\n\n_(stopped.)_" : "Stopped before any answer arrived.")
      } else if (text) {
        // Partial answer stands — never append a second bot turn over it.
        setBotText(text + "\n\n_(connection lost — showing what arrived.)_")
        toast.error("Could not reach the server: " + err.message)
      } else {
        setBotText("Could not reach the server: " + err.message, { error: true })
      }
    } finally {
      finalizedRef.current = true
      setStreaming(false)
      stopWork(botIdx, aborted)
      scrollIfStuck()
      // The save itself runs in the effect below: it must see the LAST chunk's
      // commit, and turnsRef lags a render inside finally.
      justFinishedRef.current = true
      setSaveTick((n) => n + 1)
    }
  }, [brain, persistChat, startWork, addWorkStep, stopWork])

  // Persist every finished ask (legacy saveHistory runs after finalize, not
  // only on failures), and again when late-arriving citations change the turn.
  // Runs post-commit so the saved turns include the final streamed text.
  const justFinishedRef = useRef(false)
  useEffect(() => {
    if (streaming || !justFinishedRef.current) return
    justFinishedRef.current = false
    if (turnsRef.current.length) void persistChat()
    // persistChat is called conditionally, so the linter cannot see that it is
    // a real dependency: a new brain changes which chat is remembered.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [streaming, saveTick, persistChat])

  const handleSend = (q: string, files: File[] = []) => {
    if (!q.trim() && files.length === 0) return
    ask(q, files)
  }
  const handleStop = () => {
    // Abort only: the ask's catch renders the legacy terminal state
    // ("_(stopped.)_" / "Stopped before any answer arrived.") and marks the log.
    ;(window as unknown as { CONTROLLER?: AbortController }).CONTROLLER?.abort()
  }
  const openView = (v: "chat" | "brains" | "connectors" | "graph") => {
    setView(v)
    const u = new URL(location.href)
    if (v === "chat") u.searchParams.delete("view")
    else u.searchParams.set("view", v)
    // Legacy carries ?brain= through every in-app link (shell.js:43), so the
    // view a user lands on is about the brain they were looking at.
    if (brain && brain !== DEFAULT_BRAIN) u.searchParams.set("brain", brain)
    history.pushState(null, "", u)
  }
  const handleBrainChange = (b: string) => {
    if (b === "__upload__") { setCreateOpen(true); return }
    // CH-14: the conversation on screen belongs to the brain it was asked in.
    // Nothing cleared it, so switching brains left brain A's thread visible
    // under brain B — and the next save filed that conversation into B. An
    // in-flight answer made it worse: its chunks kept writing into the thread
    // the user had just abandoned. The switcher's own confirm text promises
    // "this starts a fresh chat"; now the code does it.
    ;(window as unknown as { CONTROLLER?: AbortController }).CONTROLLER?.abort()
    // -1 makes every write from the abandoned ask a no-op (setBotText checks the
    // index before touching a turn), so a late chunk cannot reappear anywhere.
    botIdxRef.current = -1
    // Cleared on the ref as well as in state: the aborted ask's save effect can
    // fire before React commits setTurns([]), and a stale turnsRef would have
    // filed brain A's conversation under brain B with a brand-new id.
    turnsRef.current = []
    setTurns([])
    setChatId(null)
    openView("chat")
    setBrain(b)
    const u = new URL(location.href)
    u.searchParams.set("brain", b)
    u.searchParams.delete("chat")
    history.pushState(null, "", u)
  }
  const openChat = async (id: string, chatBrain?: string) => {
    // Legacy aborts the in-flight answer and lets it settle before swapping
    // threads (static/index.html:1965-1968). Without this the old stream keeps
    // writing through botIdxRef into the conversation just opened.
    ;(window as unknown as { CONTROLLER?: AbortController }).CONTROLLER?.abort()
    await new Promise((resolve) => setTimeout(resolve, 200))
    const target = chatBrain ?? brain

    // One history entry and no contradictions: opening a saved chat is not
    // "starting a new one", so ?new goes; ?chat and ?brain describe what is on
    // screen. (This used to call handleBrainChange — which clears the chat and
    // pushes its own entry — and then push a second one.)
    setBrain(target)
    setView("chat")
    setChatId(id)
    const u = new URL(location.href)
    u.searchParams.set("chat", id)
    u.searchParams.set("brain", target)
    u.searchParams.delete("new")
    // The URL must agree with the state: `view` is only present for a NON-chat
    // view (see openView). Leaving `?view=brains` behind made a reload land on
    // the Brains page with the conversation loaded but invisible — the audit's
    // "clicking a chat from another section does nothing you can see", and it
    // only showed up after a reload, which is why it survived the port.
    u.searchParams.delete("view")
    history.pushState(null, "", u)

    setSwitching(true)
    try {
      setTurns(await fetchChat(id))
      setMobileOpen(false)
    } catch (e) {
      // A chat that is gone — deleted here, deleted in another tab, or not
      // ours — left the app sitting on a screen that never changed and never
      // explained itself, with the dead id still in the URL.
      setTurns([])
      setChatId(null)
      const back = new URL(location.href)
      back.searchParams.delete("chat")
      history.replaceState(null, "", back)
      toast.error("Could not open that chat: " + (e as Error).message)
      refreshChats()
    } finally {
      // The switch dimmer must clear on every path, or the app stays dimmed.
      setSwitching(false)
    }
  }
  const newChat = () => {
    // Clearing the conversation is not the same as leaving the section it was
    // started from. This used to delete ?chat and set ?new=1 and nothing else, so
    // clicking "New chat" from Brains, Connectors or Graph pushed the
    // contradiction `?view=brains&new=1`, left the other view on screen, and
    // reloaded straight back to it — the owner's report exactly, and the same
    // defect CH-4 already fixed in openChat but never looked for in its sibling.
    // openView is the one place that keeps `view` state and the URL in agreement
    // (the param exists only for a NON-chat view), so the URL is built to that
    // contract instead of beside it.
    // Abandon any answer still streaming, exactly as handleBrainChange does.
    // Without this the old stream kept writing through the shared botIdxRef into
    // whatever conversation appeared next: "New chat", "Clear conversation" and
    // "Delete chat" all call here, so a slow answer plus a click produced the old
    // answer's text inside the new thread, flipped the composer back to Send
    // mid-question, froze the new turn's working timer, and then SAVED the
    // mixture. A single shared index is the whole hazard; -1 is the fence.
    const w = window as unknown as { CONTROLLER?: AbortController }
    w.CONTROLLER?.abort()
    botIdxRef.current = -1
    turnsRef.current = []
    setStreaming(false)
    openView("chat")
    const u = new URL(location.href)
    u.searchParams.delete("chat")
    u.searchParams.set("new", "1")
    // replace, not push: openView already took the history entry for this jump,
    // and a second push would make Back land on a view the user never saw.
    history.replaceState(null, "", u)
    setChatId(null)
    setTurns([])
    // These two belong to the section being left, not to a fresh conversation.
    // /upload lands on ?view=brains&new=1 with the create dialog open, so without
    // this "New chat" returned the composer to the screen behind a modal.
    setCreateOpen(false)
    setFilesOpen(false)
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
      // The box grew for a long question; without this it stays tall forever.
      const el = qRef.current
      if (el) { el.style.height = "auto" }
    }
  }

  const addFiles = (list: FileList | null) => {
    if (!list?.length) return
    const keep: File[] = []
    for (const f of Array.from(list)) {
      if (f.size > MAX_ATTACH_BYTES) {
        toast.warning(`${f.name} is ${(f.size / 1048576).toFixed(1)} MB — over the 8 MB limit, so it was not attached.`)
        continue
      }
      if (pendingFiles.length + keep.length >= 6) {
        toast.warning("Up to 6 files ride one message. The rest were not attached.")
        break
      }
      keep.push(f)
    }
    if (keep.length) setPendingFiles((cur) => [...cur, ...keep].slice(0, 6))
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

  // Theme helpers — the tick marks the stored MODE, not the resolved theme, or
  // "System default" could never show as selected (legacy compares KTheme.theme).
  const [currentTheme, setCurrentThemeState] = useState<"system" | "dark" | "light">(
    () => (localStorage.getItem("kestrel.theme") as "system" | "dark" | "light") || "system",
  )
  useEffect(() => {
    const onTheme = (e: Event) => {
      const detail = (e as CustomEvent<{ theme?: string }>).detail
      setCurrentThemeState((detail?.theme as "system" | "dark" | "light") || "system")
    }
    window.addEventListener("kestrel:theme", onTheme)
    return () => window.removeEventListener("kestrel:theme", onTheme)
  }, [])

  // Language helpers
  const currentLang = lang
  const openSubMenu = (which: "lang" | "theme") => {
    const pop = document.querySelector<HTMLElement>(".settings-pop")
    const r = pop?.getBoundingClientRect()
    const width = 200
    let left = r ? r.right + 8 : 12
    if (left + width > window.innerWidth - 8) left = r ? Math.max(8, r.left - width - 8) : 12
    setSubMenuPos({ left, bottom: r ? Math.max(10, window.innerHeight - r.bottom) : 72 })
    setSettingsOpen(false)
    if (which === "lang") { setThemeMenuOpen(false); setLangMenuOpen(true) }
    else { setLangMenuOpen(false); setThemeMenuOpen(true) }
  }

  // Escape and outside clicks close the submenus, like the settings pop itself.
  useEffect(() => {
    if (!langMenuOpen && !themeMenuOpen) return
    const close = () => { setLangMenuOpen(false); setThemeMenuOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close() }
    const onClick = (e: MouseEvent) => {
      const el = e.target as HTMLElement | null
      if (el?.closest(".sub-pop")) return
      close()
    }
    // Registered on the NEXT task: React flushes passive effects for a discrete
    // event before that event finishes propagating, so a listener added here
    // synchronously receives the very click that opened the menu and closes it
    // again (observed: the submenu flashed and vanished).
    const id = window.setTimeout(() => {
      document.addEventListener("keydown", onKey)
      document.addEventListener("click", onClick)
    }, 0)
    return () => {
      window.clearTimeout(id)
      document.removeEventListener("keydown", onKey)
      document.removeEventListener("click", onClick)
    }
  }, [langMenuOpen, themeMenuOpen])

  const changeLang = (code: LangCode) => {
    setLang(code)
    setLangState(code)
    setGreet(greetFor())
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
    void copyText(transcript(turns, "md")).then((ok) => {
      if (!ok) toast.warning("Copy failed — select the text and copy manually.")
    })
    setMenu2Open(false)
  }

  // Legacy clear-chat: two-step armed confirm, then this chat is deleted
  // server-side and the thread resets to home.
  const handleClearChat = async () => {
    if (!clearArmed) {
      setClearArmed(true)
      // Legacy disarms the armed state on its own after 3.5s (index.html:1837).
      window.setTimeout(() => setClearArmed(false), 3500)
      return
    }
    setClearArmed(false)
    setDraft(null)
    setMenu2Open(false)
    const id = chatId
    if (id) {
      // CH-3: "clear chat" IS a delete, and this call used to discard the
      // response entirely — a delete that removed nothing still looked like
      // success, and the chat was waiting in the sidebar on the next list.
      // A 404 is tolerated here: the chat is already gone, which is the goal.
      try {
        const r = await apiFetch(`/api/chats/${encodeURIComponent(id)}`, { method: "DELETE" })
        if (!r.ok && r.status !== 404) {
          toast.error("Could not delete this chat: " + await serverError(r))
        }
      } catch (e) {
        toast.error("Could not delete this chat: " + (e as Error).message)
      }
    }
    newChat()
    refreshChats()
  }

  // Delete handlers
  const handleDeleteChat = async (targetId: string, _brain?: string) => {
    try {
      const r = await apiFetch(`/api/chats/${encodeURIComponent(targetId)}`, { method: "DELETE" })
      if (!r.ok) throw new Error(await serverError(r))
      // A delete that gives no feedback is indistinguishable from one that did
      // nothing — especially here, where the next chat in the folder slides
      // into the row that just disappeared.
      toast.success(t("chat.deleted", "Chat deleted"))
    } catch (e) {
      toast.error("Could not delete the chat: " + (e as Error).message)
    }
    if (targetId === chatId) newChat()
    refreshChats()
  }
  const handleDeleteBrainChats = async (targetBrain: string) => {
    try {
      // limit=500: deleting "all chats in this brain" must not stop at the
      // API's default page size and report success.
      const r = await apiFetch(`/api/chats?brain=${encodeURIComponent(targetBrain)}&limit=500`)
      if (!r.ok) throw new Error(await serverError(r))
      const d = await r.json()
      const list: { id: string }[] = d.chats || []
      let failed = 0
      for (const c of list) {
        try {
          const dr = await apiFetch(`/api/chats/${encodeURIComponent(c.id)}`, { method: "DELETE" })
          if (!dr.ok) failed += 1
        } catch {
          failed += 1
        }
      }
      if (failed) {
        toast.warning(`Deleted ${list.length - failed} of ${list.length} chats — ${failed} failed.`)
      } else if (list.length) {
        toast.success(`Deleted ${list.length} chat(s) from ${targetBrain}`)
      }
    } catch (e) {
      toast.error("Could not delete the chats: " + (e as Error).message)
    }
    if (targetBrain === brain) newChat()
    refreshChats()
  }

  // Message actions (legacy .msg-acts: copy with sources, quiet feedback marks)
  const copyAnswer = (i: number) => {
    const turn = turns[i]
    if (!turn) return
    const names = (turn.sources || []).map((s) => s.source).filter(Boolean)
    void copyText(cleanText(turn.text) + (names.length ? "\n\nSources: " + names.join(", ") : "")).then((ok) => {
      if (!ok) { toast.warning("Copy failed — select the text and copy manually."); return }
      setCopiedIdx(i)
      // Legacy also flips the button's title to "Copied" (index.html:1131).
      setTimeout(() => setCopiedIdx((cur) => (cur === i ? null : cur)), 1300)
    })
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
      const r = await apiFetch("/api/actions/draft", {
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

  // Legacy filters internal brains out of the switcher and sorts demo-first
  // (index.html:760-763). `_*`/`default` datasets are plumbing, not choices.
  const isDemoBrain = (name: string) => name === "demo" || name === DEFAULT_BRAIN
  const brainOptions = (() => {
    const usable = brains.filter((b) => !b.is_system)
    return usable.slice().sort((a, b) => {
      const da = isDemoBrain(a.name) ? 0 : 1
      const db = isDemoBrain(b.name) ? 0 : 1
      return da - db || a.name.localeCompare(b.name)
    })
  })()

  const brainLabel = !brain || brain === "demo" || brain === DEFAULT_BRAIN ? "Demo brain" : brain
  // Legacy picks the generic starters only for a non-demo brain.
  const chipSource = brain && brain !== "demo" && brain !== DEFAULT_BRAIN ? GENERIC_CHIPS : DEMO_CHIPS
  const chips = chipSource.map((c) => ({ ...c, label: t(c.labelKey, c.label) }))
  const questionCount = turns.filter((turn) => turn.role === "user").length
  const goClass = streaming ? "stop" : ""

  const renderTurn = (turn: Turn, i: number) => {
    if (turn.role === "user") {
      return (
        <div
          className="turn user"
          key={i}
          data-uid={i}
          ref={(el) => { turnEls.current[i] = el }}
        >
          <div className="bubble">
            {/* Legacy .turn.user .bubble .atts (shell.css:147): the files the
                question was about ride the message, and survive a reload for
                anything small enough to snapshot (legacy:1526-1532). */}
            {turn.attachments && turn.attachments.length > 0 && (
              <div className="atts">
                {turn.attachments.map((a, ai) => (
                  <div
                    className="att"
                    key={`${a.name}-${ai}`}
                    title={a.url ? a.name : `${a.name} — session only (too large to store)`}
                    role={a.url ? "button" : undefined}
                    tabIndex={a.url ? 0 : undefined}
                    onClick={() => { if (a.url) window.open(a.url, "_blank", "noopener") }}
                    onKeyDown={(e) => {
                      if (a.url && (e.key === "Enter" || e.key === " ")) {
                        e.preventDefault()
                        window.open(a.url, "_blank", "noopener")
                      }
                    }}
                  >
                    {a.kind === "image" && a.url ? (
                      <img src={a.url} alt={a.name} />
                    ) : (
                      <div className="att-file">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d={DOC_D} /></svg>
                        <span>{a.name}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            {turn.text}
          </div>
        </div>
      )
    }
    const isLast = i === turns.length - 1
    const streamingHere = streaming && isLast
    const steps = turn.steps || []
    // The log is this turn's own (legacy keeps one per answer); only the live
    // turn is "working", and a finished one collapses into its header.
    const logDone = !streamingHere && steps.length > 0
    const logOpen = expandedLogs[i] ?? !logDone
    const workedSeconds = streamingHere
      ? workElapsed
      : (turn.workedMs != null ? turn.workedMs / 1000 : 0)
    return (
      <div className="turn bot" key={i} data-uid={i} ref={(el) => { turnEls.current[i] = el }}>
        {steps.length > 0 && (
          <div className={"working" + (logDone && !logOpen ? " collapsed" : "")}>
            <div
              className={"working-head" + (logDone ? " toggle" : "")}
              title={logDone ? (logOpen ? "Hide the steps" : "Show the steps") : undefined}
              role={logDone ? "button" : undefined}
              tabIndex={logDone ? 0 : undefined}
              aria-expanded={logDone ? logOpen : undefined}
              onClick={logDone ? () => setExpandedLogs((prev) => ({ ...prev, [i]: !logOpen })) : undefined}
              onKeyDown={logDone ? (e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault()
                  setExpandedLogs((prev) => ({ ...prev, [i]: !logOpen }))
                }
              } : undefined}
            >
              {!logDone && <span className="spin" />}
              <span className="w-elapsed">{(logDone ? "Worked · " : "Working · ") + workedSeconds.toFixed(1) + "s"}</span>
              {turn.stopped && <span className="w-stopped">· stopped</span>}
            </div>
            {steps.map((st, si) => {
              if (st.label === "stopped") return null
              const live = !logDone && si === steps.length - 1
              const endAt = steps[si + 1]?.at ?? (logDone ? (turn.at || 0) + (turn.workedMs || 0) : Date.now())
              const dur = (st.ms != null ? (st.ms / 1000).toFixed(1) : ((endAt - st.at) / 1000).toFixed(1)) + "s"
              return (
                <div key={si} className={"w-step " + (live ? "live" : "done")}>
                  {live ? st.label : "✓ " + st.label + " · " + dur}
                </div>
              )
            })}
          </div>
        )}
        {/* Legacy .bubble.err (static/index.html:1423-1424, shell.css:258):
            a failure is an error state, not model output. Rendering it as
            markdown made "Something went wrong" read like an answer. */}
        <div className={"bubble rendered" + (streamingHere ? " streaming" : "") + (turn.error ? " err" : "")}>
          {turn.text ? (
            <Suspense fallback={<span>{turn.text}</span>}>
              <Markdown
                sources={turn.sources}
                onOpenSource={(item) => setSourcesPanel({ title: item.source, excerpt: item.excerpt, version: item.version })}
              >
                {turn.text}
              </Markdown>
            </Suspense>
          ) : null}
        </div>
        {turn.sources && turn.sources.length > 0 && (
          <div className="srcs">
            {turn.sources.map((s, si) => (
              <CitationChip
                key={si}
                index={si + 1}
                source={s}
                onOpenSource={(item) => setSourcesPanel({ title: item.source, excerpt: item.excerpt, version: item.version })}
              />
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
            {/* Legacy: new Date(at) — restored turns keep the time they were
                said, instead of being stamped with the current clock. */}
            <span className="time">{new Date(turn.at || Date.now()).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span>
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
        <Menu className="h-5 w-5" aria-hidden="true" />
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
        chatsError={chatsError}
        chatsTotal={chatsTotal}
        chatsTruncated={chatsTruncated}
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

      {/* role="main" rather than a <main> element: DESIGN.md lists landmarks as an
          accessibility requirement, and the skip link had nowhere to land. The
          element is left as a div on purpose — retagging it means reparsing every
          sibling's closing tag in this tree, and assistive tech gets the same
          region either way. */}
      <div className="app-main" id="kestrel-main" role="main">
        <h1 className="sr-only">Kestrel Company Brain</h1>
        {view === "connectors" ? (
          <Connectors brain={brain} />
        ) : view === "graph" ? (
          <GraphView brain={brain} />
        ) : view === "brains" ? (
          <BrainsPage
            onAddDocuments={(name) => {
              // "Add documents" on a brain row: make that the active brain and
              // open the sheet on the chat surface (the sheet adds to the
              // CURRENT brain, so the two must agree).
              //
              // Switching brain while a conversation is on screen is the CH-14
              // situation, and this route used to skip every part of the answer
              // handleBrainChange already applies: it set the brain, left ?chat=
              // in the URL and left the turns in state. The next question then
              // saved brain A's thread under brain B — the server re-stamps the
              // brain unconditionally (storage.py:341) — and a stream still in
              // flight kept writing into a conversation the user had abandoned.
              // It also wrote ?view=chat, which openView deletes for exactly this
              // param's sake: `view` exists only to name a NON-chat view.
              const w = window as unknown as { CONTROLLER?: AbortController }
              w.CONTROLLER?.abort()
              botIdxRef.current = -1
              turnsRef.current = []
              setBrain(name)
              setChatId(null)
              setTurns([])
              openView("chat")
              const u = new URL(location.href)
              u.searchParams.delete("chat")
              u.searchParams.delete("new")
              u.searchParams.set("brain", name)
              history.replaceState(null, "", u)
              setFilesOpen(true)
            }}
          />
        ) : (
          <>
            <div id="home">
              <div className="watermark">◆</div>
              <div className="greeting" id="greeting">{greet}</div>
            </div>
            <div id="thread-wrap">
              <div className="wrap">
                <div id="thread">
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
                          <img src={attachmentPreviews[i] || ""} alt={f.name} />
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
                  {clearArmed ? t("menu.really_clear", "Really clear?") : t("menu.clear_chat", "Clear conversation")}
                </button>
              </div>

              <div className="pop" id="brainmenu" hidden={!brainMenuOpen}>
                <div className="pop-note">Ask in</div>
                {brainsError && <div className="count err">{brainsError}</div>}
                {brainOptions.map((b) => {
                  const isCurrent = b.name === brain
                  const armed = brainSwitchArmed === b.name
                  return (
                    <button
                      type="button"
                      key={b.name}
                      className={armed ? "armed" : undefined}
                      title={armed ? "Click again — this starts a fresh chat" : undefined}
                      onClick={(e) => {
                        e.stopPropagation()
                        if (isCurrent) { setBrainSwitchArmed(null); setBrainMenuOpen(false); return }
                        // A live conversation is not silently relabelled: the
                        // first click arms, the second switches.
                        if (turns.length > 0 && !armed) { setBrainSwitchArmed(b.name); return }
                        setBrainSwitchArmed(null)
                        handleBrainChange(b.name)
                        setBrainMenuOpen(false)
                      }}
                    >
                      <span>
                        {isDemoBrain(b.name) ? t("brain.demo", "Demo brain") : b.name}
                        {b.is_demo ? " · demo" : ""}
                        {armed ? " — start a fresh chat?" : ""}
                      </span>
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
            <button
              type="button"
              className="chip"
              key={c.label}
              onClick={() => {
                // Legacy writes the starter into #q and lets the user send it
                // (index.html:812) — asking straight away removed the chance to
                // edit the question.
                setInput(c.query)
                requestAnimationFrame(() => { growQ(); qRef.current?.focus() })
              }}
            >
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
          stickRef.current = true
          scrollBottom()
          qRef.current?.focus()
        }}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d={JUMP_D} /></svg>
      </button>

      {/* One announcement per finished answer, instead of a screen reader
          re-reading the whole thread on every streamed token. */}
      <div className="sr-only" role="status" aria-live="polite">
        {!streaming && turns.length > 0 && turns[turns.length - 1]?.role === "bot"
          ? t("a11y.answer_ready", "Answer ready.")
          : ""}
      </div>

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
          version={sourcesPanel.version}
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
        onLanguage={() => openSubMenu("lang")}
        onTheme={() => openSubMenu("theme")}
        onUsage={() => { setSettingsOpen(false); setUsageOpen(true) }}
        onUpgrade={() => { setSettingsOpen(false); setUpgradeOpen(true) }}
        onConnectors={() => { setSettingsOpen(false); openView("connectors") }}
        onAccount={() => { setSettingsOpen(false); clerkOpenProfile() }}
        onSignOut={() => { setSettingsOpen(false); clerkSignOut() }}
        signedIn={signedIn}
      />

      <UsageModal open={usageOpen} onClose={() => setUsageOpen(false)} />
      <UpgradeModal open={upgradeOpen} onClose={() => setUpgradeOpen(false)} />

      {/* Language sub-menu */}
      {langMenuOpen && (
        <PopMenu
          className="sub-pop fixed z-[90] min-w-[190px] rounded-xl border border-line-2 bg-panel p-1.5 shadow-lg"
          style={subMenuPos ? { left: subMenuPos.left, bottom: subMenuPos.bottom } : undefined}
        >
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
        <PopMenu
          className="sub-pop fixed z-[90] min-w-[190px] rounded-xl border border-line-2 bg-panel p-1.5 shadow-lg"
          style={subMenuPos ? { left: subMenuPos.left, bottom: subMenuPos.bottom } : undefined}
        >
          <div className="px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground">
            {t("set.theme", "App theme")}
          </div>
          {(["system", "dark", "light"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-[13px] text-fg-2 transition-colors hover:bg-wash hover:text-fg"
              onClick={() => { setTheme(mode); setCurrentThemeState(mode); setThemeMenuOpen(false) }}
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
