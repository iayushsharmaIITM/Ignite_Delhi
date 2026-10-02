import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { PanelLeft } from "lucide-react"
import { Sidebar } from "@/components/Sidebar"
import { PromptBox } from "@/components/PromptBox"
import { Connectors } from "@/components/Connectors"
import { SourceDrawer } from "@/components/SourceDrawer"
import { CreateBrainDialog } from "@/components/CreateBrainDialog"
import { GraphView } from "@/components/GraphView"
import { Toaster } from "@/components/ui/sonner"
import { Button } from "@/components/ui/button"
import {
  TurnRise,
  PopMenu,
  JumpToLatest,
  LeftRail,
  RestoreOverlay,
  SwitchFx,
  SuggestionChips,
  Watermark,
  AuthGate,
  SettingsMenu,
  ExportMenu,
  MessageActions,
  WorkingLog,
  type WorkStep,
} from "@/components/Animations"
import {
  DEFAULT_BRAIN,
  greeting,
  useBrains,
  useChats,
  fetchChat,
  saveChat,
} from "@/lib/api"
import { cn } from "@/lib/utils"
import { t, setLang, getLang, getLangs, type LangCode } from "@/lib/i18n"
import { resolvedTheme, applyTheme, setTheme } from "@/theme"
import { loadClerk } from "@/lib/clerk"

const Markdown = lazy(() => import("@/components/Markdown"))

type Source = { source: string; excerpt?: string }
type Turn = { role: "user" | "bot"; text: string; sources?: Source[] }

const DEMO_CHIPS = [
  { label: t("chip.demo1", "Why is the Bluepeak renewal at risk?"), query: "Why is the Bluepeak renewal at risk, and what have we promised them?" },
  { label: t("chip.demo2", "What credit do we owe, and who approved it?"), query: "What service credit do we owe Bluepeak, and who approved it?" },
  { label: t("chip.demo3", "Who owns the renewal and the RCA?"), query: "Who owns the Bluepeak renewal, and who owns the root cause analysis?" },
  { label: t("chip.demo4", "Is the renewal date consistent?"), query: "Is the Bluepeak renewal date consistent across our documents?" },
]

const GENERIC_CHIPS = [
  { label: t("chip.gen1", "Summarise what is in this brain"), query: "Summarise what this brain knows — its main documents and topics." },
  { label: t("chip.gen2", "What are the next steps?"), query: "What are the next steps across my documents, and who owns each one?" },
  { label: t("chip.gen3", "Draft a mail from the latest answer"), query: "Draft a mail summarising the most recent answer." },
  { label: t("chip.gen4", "Is everything consistent?"), query: "Is everything in this brain consistent with each other?" },
]

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
    localStorage.getItem("kestrel.sidebar.collapsed") === "1" || window.innerWidth < 768,
  )
  const [brain, setBrain] = useState(
    new URLSearchParams(location.search).get("brain") || DEFAULT_BRAIN,
  )
  const [turns, setTurns] = useState<Turn[]>([])
  const [streaming, setStreaming] = useState(false)
  const [input, setInput] = useState("")
  const [sourcesPanel, setSourcesPanel] = useState<{ title: string; excerpt?: string } | null>(null)
  const [stage, setStage] = useState<string | null>(null)
  const chatIdRef = useRef<string | null>(null)
  const turnsRef = useRef<Turn[]>([])
  useEffect(() => { turnsRef.current = turns }, [turns])
  const threadRef = useRef<HTMLDivElement>(null)
  const [greet, setGreet] = useState(greeting())
  const [chatId, setChatId] = useState<string | null>(
    new URLSearchParams(location.search).get("chat"),
  )
  useEffect(() => { chatIdRef.current = chatId }, [chatId])

  // Animation / UI state
  const [restoring, setRestoring] = useState(false)
  const [switching, setSwitching] = useState(false)
  const [jumpVisible, setJumpVisible] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [exportMenuOpen, setExportMenuOpen] = useState(false)
  const [langMenuOpen, setLangMenuOpen] = useState(false)
  const [themeMenuOpen, setThemeMenuOpen] = useState(false)
  const [workSteps, setWorkSteps] = useState<WorkStep[]>([])
  const [workElapsed, setWorkElapsed] = useState(0)
  const workStartRef = useRef(0)
  const workTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [signedIn, setSignedIn] = useState(false)
  const [authMode, setAuthMode] = useState<string>("unknown")

  // deep-link restore: ?chat=<id> loads the server-backed thread on mount
  useEffect(() => {
    const id = new URLSearchParams(location.search).get("chat")
    if (!id) return
    setRestoring(true)
    fetchChat(id)
      .then((serverTurns) => {
        if (serverTurns.length) setTurns(serverTurns)
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

  // Scroll tracking for jump-to-latest
  useEffect(() => {
    const onScroll = () => {
      const stick = window.innerHeight + window.scrollY >= document.body.scrollHeight - 160
      setJumpVisible(!stick && turns.length > 0)
    }
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [turns.length])

  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth < 768) setCollapsed(true)
    }
    window.addEventListener("resize", onResize)
    return () => window.removeEventListener("resize", onResize)
  }, [])
  const [createOpen, setCreateOpen] = useState(false)
  const [view, setView] = useState<"chat" | "connectors" | "graph">(
    new URLSearchParams(location.search).get("view") === "connectors" ? "connectors"
    : new URLSearchParams(location.search).get("view") === "graph" ? "graph" : "chat",
  )
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
    const t = setInterval(() => setGreet(greeting()), 60000)
    return () => clearInterval(t)
  }, [])

  const scrollBottom = () => {
    requestAnimationFrame(() =>
      threadRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }),
    )
  }

  const startWork = () => {
    workStartRef.current = Date.now()
    setWorkElapsed(0)
    setWorkSteps([])
    if (workTimerRef.current) clearInterval(workTimerRef.current)
    workTimerRef.current = setInterval(() => {
      setWorkElapsed((Date.now() - workStartRef.current) / 1000)
    }, 100)
  }

  const addWorkStep = (label: string, ms?: number) => {
    setWorkSteps((prev) => [...prev, { label, ms }])
  }

  const stopWork = (stopped?: boolean) => {
    if (workTimerRef.current) {
      clearInterval(workTimerRef.current)
      workTimerRef.current = null
    }
    if (stopped) {
      setWorkSteps((prev) => [...prev, { label: "stopped" }])
    }
  }

  const ask = useCallback(async (q: string, files: File[] = []) => {
    setTurns((t) => [...t, { role: "user", text: q }])
    setStreaming(true)
    startWork()
    addWorkStep(t("stage.smalltalk", "Direct chat — no retrieval needed"))
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
        setStage("Reading attached files…")
        const context = await buildContext(files, controller.signal)
        if (context) params.set("context", context)
        const ingestible = files.filter((f) => !(f.type || "").startsWith("image/"))
        if (brain && brain !== "demo" && ingestible.length) {
          addWorkStep(`Adding ${ingestible.length} file(s) to ${brain}…`)
          setStage(`Adding ${ingestible.length} file(s) to ${brain}…`)
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
      addWorkStep(t("stage.plan", "Planning retrieval agents"))
      setStage("Thinking…")
      const res = await fetch(`/api/ask?${params}`, { signal: controller.signal })
      const reader = res.body!.getReader()
      const dec = new TextDecoder()
      let buf = ""
      let botIdx = -1
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
            if (botIdx < 0) {
              setTurns((t) => {
                botIdx = t.length
                return [...t, { role: "bot", text }]
              })
            } else {
              setTurns((t) => {
                const copy = [...t]
                if (copy[botIdx]) copy[botIdx] = { role: "bot", text }
                return copy
              })
            }
            scrollBottom()
          } else if (ev.type === "references") {
            const items: Source[] = (ev.items || []).map((s: { source?: string; excerpt?: string }) => ({
              source: s.source || "source",
              excerpt: s.excerpt,
            }))
            setTurns((t) => {
              const copy = [...t]
              const idx = botIdx >= 0 ? botIdx : copy.length - 1
              if (copy[idx]?.role === "bot") copy[idx] = { ...copy[idx], sources: items }
              return copy
            })
          } else if (ev.stage === "error") {
            text += (text ? "\n\n" : "") + "⚠️ " + (ev.message || "The request failed.")
            if (botIdx < 0) {
              setTurns((t) => {
                botIdx = t.length
                return [...t, { role: "bot", text }]
              })
            } else {
              setTurns((t) => {
                const copy = [...t]
                if (copy[botIdx]) copy[botIdx] = { role: "bot", text }
                return copy
              })
            }
          } else if (ev.stage && ev.stage !== "done" && !ev.message) {
            const stageLabel =
              ev.stage === "start" ? t("stage.router_chat", "Searching the brain…") :
              ev.stage === "ready" ? t("stage.delegating", "Composing the answer…") :
              ev.label || ev.stage
            addWorkStep(stageLabel)
            setStage(stageLabel)
          }
        }
      }
    } catch (e) {
      const err = e as Error
      if (err.name !== "AbortError") {
        setTurns((t) => [...t, { role: "bot", text: "Could not reach the server: " + err.message }])
      }
      const id = chatIdRef.current || (chatIdRef.current = crypto.randomUUID())
      const firstUser = turnsRef.current.find((t) => t.role === "user")
      void saveChat(id, firstUser ? firstUser.text : "Untitled", brain, turnsRef.current)
        .then((ok) => ok && refreshChats())
    } finally {
      setStreaming(false)
      setStage(null)
      stopWork()
      scrollBottom()
    }
  }, [brain])

  const handleSend = (q: string, files: File[] = []) => {
    if (!q.trim()) return
    setInput(q)
    ask(q, files)
  }
  const handleStop = () => {
    ;(window as unknown as { CONTROLLER?: AbortController }).CONTROLLER?.abort()
    stopWork(true)
  }
  const openView = (v: "chat" | "connectors" | "graph") => {
    setView(v)
    const u = new URL(location.href)
    if (v === "chat") u.searchParams.delete("view")
    else u.searchParams.set("view", v)
    history.pushState(null, "", u)
  }
  const handleBrainChange = (b: string) => {
    if (b === "__upload__") { setCreateOpen(true); return }
    if (b === "__graph__") {
      if (confirm("The knowledge-graph view still lives in the legacy shell. Open it?")) {
        location.href = `/graph${brain ? `?brain=${encodeURIComponent(brain)}` : ""}`
      }
      return
    }
    setChatId(null)
    openView("chat")
    setBrain(b)
    const u = new URL(location.href)
    u.searchParams.set("brain", b)
    history.pushState(null, "", u)
  }
  const openChat = async (id: string, chatBrain: string) => {
    setSwitching(true)
    handleBrainChange(chatBrain)
    const u = new URL(location.href)
    u.searchParams.set("chat", id)
    history.pushState(null, "", u)
    setChatId(id)
    const serverTurns = await fetchChat(id)
    if (serverTurns.length) setTurns(serverTurns)
    else setTurns([])
    setSwitching(false)
    if (window.innerWidth < 768) setCollapsed(true)
  }
  const newChat = () => {
    const u = new URL(location.href)
    u.searchParams.delete("chat")
    u.searchParams.set("new", "1")
    history.pushState(null, "", u)
    setChatId(null)
    setTurns([])
  }

  const hasInput = input.trim().length > 0

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

  // Export handlers
  const handleExportMd = () => {
    downloadFile("kestrel-conversation.md", transcript(turns, "md"), "text/markdown")
    setExportMenuOpen(false)
  }
  const handleExportTxt = () => {
    downloadFile("kestrel-conversation.txt", transcript(turns, "txt"), "text/plain")
    setExportMenuOpen(false)
  }
  const handleExportDocx = () => {
    const md = transcript(turns, "md")
    const html = '<html xmlns:w="urn:schemas-microsoft-com:office:word"><head><meta charset="utf-8"><title>Kestrel conversation</title></head><body>' + md.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>") + "</body></html>"
    downloadFile("kestrel-conversation.doc", html, "application/msword")
    setExportMenuOpen(false)
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
    setExportMenuOpen(false)
  }
  const handleCopyTranscript = () => {
    navigator.clipboard.writeText(transcript(turns, "md")).catch(() => {})
    setExportMenuOpen(false)
  }

  // Message action handlers
  const handleEmailDraft = (turnText: string) => {
    const subject = "Kestrel answer"
    const body = cleanText(turnText)
    window.open(`mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`, "_self")
  }
  const handleSteps = (turnText: string) => {
    const steps = turnText.split("\n").filter((l) => /^\s*[-*•]\s+/.test(l)).map((l) => l.replace(/^\s*[-*•]\s+/, ""))
    if (steps.length) {
      alert("Next steps:\n\n" + steps.map((s) => "• " + s).join("\n"))
    } else {
      alert("No explicit next steps found in this answer.")
    }
  }
  const handleChatUpdate = (turnText: string) => {
    const summary = cleanText(turnText).slice(0, 500)
    navigator.clipboard.writeText(summary).then(() => {
      toast.success(t("common.copied", "Copied!"))
    }).catch(() => {})
  }

  // Delete handlers
  const handleDeleteChat = async (chatId: string, _chatBrain: string) => {
    try {
      await fetch(`/api/chats/${encodeURIComponent(chatId)}`, { method: "DELETE" })
    } catch {}
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
    refreshChats()
  }

  const chips = brain && brain !== "demo" ? GENERIC_CHIPS : DEMO_CHIPS

  return (
    <div className="flex h-full">
      <a
        href="#kestrel-main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-primary focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-primary-foreground"
      >
        Skip to chat
      </a>
      {collapsed && (
        <Button
          variant="secondary"
          size="icon"
          aria-label="Expand sidebar"
          onClick={() => {
            localStorage.setItem("kestrel.sidebar.collapsed", "0")
            setCollapsed(false)
          }}
          className="fixed left-3 top-3 z-30 rounded-lg text-muted-foreground shadow"
        >
          <PanelLeft className="h-4 w-4" />
        </Button>
      )}
      <Sidebar
        collapsed={collapsed}
        onToggle={() => {
          setCollapsed((c) => {
            localStorage.setItem("kestrel.sidebar.collapsed", c ? "0" : "1")
            return !c
          })
        }}
        currentBrain={brain}
        currentChat={chatId}
        view={view}
        onViewChange={openView}
        onBrainChange={handleBrainChange}
        onNewChat={newChat}
        onOpenChat={(id, b) => void openChat(id, b)}
        chats={chats}
        onRefreshChats={refreshChats}
        onDeleteChat={handleDeleteChat}
        onDeleteBrainChats={handleDeleteBrainChats}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenAccount={clerkOpenProfile}
        onSignOut={clerkSignOut}
        signedIn={signedIn}
      />
      <CreateBrainDialog
        open={createOpen}
        onClose={(created) => {
          setCreateOpen(false)
          refreshBrains()
          if (created) handleBrainChange(created)
        }}
      />
      <main id="kestrel-main" className="flex min-w-0 flex-1 flex-col">
        {view === "connectors" ? (
          <Connectors />
        ) : view === "graph" ? (
          <GraphView brain={brain} />
        ) : turns.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center px-6 pb-10">
            <Watermark />
            <div className="relative mb-8" aria-hidden>
              <div className="absolute inset-0 -m-6 rounded-full bg-accent-glow blur-2xl" />
              <div className="relative h-28 w-28 rotate-45 rounded-2xl border border-accent/30 bg-wash-2 shadow-[0_0_40px_rgba(232,134,59,0.12)]" />
            </div>
            <h1 className="text-[30px] font-semibold tracking-tight text-foreground">{greet}</h1>
            <div className="mt-10 w-full max-w-[820px]">
              <PromptBox
                brain={brain}
                brains={brains.map((b) => b.name)}
                onBrainChange={handleBrainChange}
                streaming={streaming}
                hasInput={hasInput}
                stage={stage}
                onSend={handleSend}
                onStop={handleStop}
              />
            </div>
            <div className="mt-6 w-full max-w-[820px]">
              <SuggestionChips
                chips={chips.map((c) => ({ label: c.label, query: c.query }))}
                onSelect={(q) => handleSend(q)}
              />
            </div>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto" aria-live="polite">
            <div ref={threadRef} className="mx-auto max-w-[780px] px-6 py-10">
              {turns.map((turn, i) => (
                <TurnRise key={i} className={cn("group/turn mb-7", turn.role === "user" && "flex justify-end")}>
                  <div
                    className={cn(
                      turn.role === "user"
                        ? "max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-wash-2 px-4 py-2.5 text-[14px] leading-relaxed text-ink-2"
                        : "text-foreground/90",
                    )}
                  >
                    {turn.role === "bot" ? (
                      <div className="max-w-none [&_a]:text-accent [&_a]:underline-offset-2 hover:[&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:border-accent/40 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground [&_code]:rounded [&_code]:bg-panel-2 [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[12.5px] [&_h2]:mb-2 [&_h2]:mt-5 [&_h2]:text-[15px] [&_h2]:font-semibold [&_h3]:mt-4 [&_h3]:text-[14px] [&_h3]:font-semibold [&_hr]:border-line [&_li]:my-1 [&_li]:marker:text-accent/70 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-3 [&_pre]:my-3 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:border [&_pre]:border-line [&_pre]:bg-panel-2 [&_pre]:p-3.5 [&_pre]:text-[12.5px] [&_pre]:leading-relaxed [&_strong]:text-ink [&_table]:my-3 [&_table]:w-full [&_table]:border-collapse [&_td]:border-b [&_td]:border-line [&_td]:px-2 [&_td]:py-1.5 [&_td]:text-[13px] [&_th]:border-b-2 [&_th]:border-line-2 [&_th]:px-2 [&_th]:py-1.5 [&_th]:text-left [&_th]:text-[10.5px] [&_th]:uppercase [&_th]:tracking-wide [&_th]:text-muted-foreground">
                        <Suspense fallback={<span className="whitespace-pre-wrap">{turn.text}</span>}><Markdown>{turn.text}</Markdown></Suspense>
                      </div>
                    ) : (
                      turn.text
                    )}
                    {streaming && i === turns.length - 1 && turn.role === "bot" && (
                      <span className="ml-0.5 inline-block h-3.5 w-[7px] translate-y-0.5 animate-pulse rounded-[2px] bg-accent/80" aria-hidden />
                    )}
                  </div>
                  {turn.role === "bot" && i === turns.length - 1 && workSteps.length > 0 && (
                    <WorkingLog steps={workSteps} elapsed={workElapsed} streaming={streaming} />
                  )}
                  {turn.role === "bot" && turn.sources && turn.sources.length > 0 && (
                    <div className="mt-3">
                      <div className="mb-1.5 text-[10.5px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
                        Grounded in {turn.sources.length} source{turn.sources.length > 1 ? "s" : ""}
                      </div>
                      <div className="flex flex-wrap gap-1.5" aria-label="Cited sources">
                        {turn.sources.map((s, si) => (
                          <button
                            key={si}
                            type="button"
                            onClick={() => setSourcesPanel({ title: s.source, excerpt: s.excerpt })}
                            className="rounded-full border border-border bg-panel px-2.5 py-1 font-mono text-[11px] text-muted-foreground transition-colors duration-150 ease-out hover:border-accent/60 hover:bg-accent-dim hover:text-accent"
                          >
                            {si + 1}. {s.source}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  {turn.role === "bot" && (
                    <MessageActions
                      onCopy={() => navigator.clipboard.writeText(turn.text)}
                      onEmail={() => handleEmailDraft(turn.text)}
                      onSteps={() => handleSteps(turn.text)}
                      onChatUpdate={() => handleChatUpdate(turn.text)}
                      onThumbsUp={() => toast.success(t("action.thumbs_up", "Helpful"))}
                      onThumbsDown={() => toast.info(t("action.thumbs_down", "Not helpful"))}
                      time={new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
                    />
                  )}
                </TurnRise>
              ))}
              {streaming && (
                <div className="mb-6 text-muted-foreground" aria-live="polite">
                  <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-primary" />
                </div>
              )}
            </div>
          </div>
        )}
        {sourcesPanel && (
          <SourceDrawer
            title={sourcesPanel.title}
            excerpt={sourcesPanel.excerpt}
            brain={brain}
            onClose={() => setSourcesPanel(null)}
          />
        )}
        {turns.length > 0 && view === "chat" && (
          <div className="sticky bottom-0 z-10 bg-gradient-to-t from-bg via-bg/95 to-transparent px-6 pb-4 pt-6 pb-[max(1rem,env(safe-area-inset-bottom))]" style={{ backgroundColor: "transparent" }}>
            <div className="pointer-events-none absolute inset-x-0 -top-8 h-8 bg-gradient-to-t from-bg to-transparent" aria-hidden />
            <PromptBox
              brain={brain}
              brains={brains.map((b) => b.name)}
              onBrainChange={handleBrainChange}
              streaming={streaming}
              hasInput={hasInput}
              stage={stage}
              onSend={handleSend}
              onStop={handleStop}
            />
          </div>
        )}
      </main>

      {/* Left rail — message scrubber */}
      {view === "chat" && turns.length > 0 && (
        <LeftRail
          turns={turns}
          onJump={(idx) => {
            const el = threadRef.current?.children[idx] as HTMLElement | undefined
            el?.scrollIntoView({ behavior: "smooth", block: "center" })
          }}
        />
      )}

      {/* Jump to latest */}
      <JumpToLatest
        visible={jumpVisible && view === "chat"}
        onClick={scrollBottom}
      />

      {/* Restore overlay */}
      <RestoreOverlay visible={restoring} />

      {/* Switch fx */}
      <SwitchFx visible={switching} />

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

      {/* Export menu */}
      <ExportMenu
        open={exportMenuOpen}
        onExportMd={handleExportMd}
        onExportTxt={handleExportTxt}
        onExportDocx={handleExportDocx}
        onExportPdf={handleExportPdf}
        onCopyTranscript={handleCopyTranscript}
      />

      <Toaster position="bottom-right" />
    </div>
  )
}
