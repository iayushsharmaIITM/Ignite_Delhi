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
import { Copy, RotateCcw } from "lucide-react"
import {
  DEFAULT_BRAIN,
  greeting,
  useBrains,
  useChats,
  fetchChat,
  saveChat,
} from "@/lib/api"
import { cn } from "@/lib/utils"

const Markdown = lazy(() => import("@/components/Markdown"))

type Source = { source: string; excerpt?: string }
type Turn = { role: "user" | "bot"; text: string; sources?: Source[] }

const CHIPS = [
  "Summarise what is in this brain",
  "What are the next steps?",
  "Draft a mail from the latest answer",
  "Is everything consistent?",
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
  const [greet, setGreet] = useState(greeting)
  const [chatId, setChatId] = useState<string | null>(
    new URLSearchParams(location.search).get("chat"),
  )
  useEffect(() => { chatIdRef.current = chatId }, [chatId])
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

  // Landing pad for the OAuth round-trip: /?connected=slack or
  // /?connect_error=<reason>. Toast, then clean the address bar.
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

  const ask = useCallback(async (q: string, files: File[] = []) => {
    setTurns((t) => [...t, { role: "user", text: q }])
    setStreaming(true)
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
        setStage("Reading attached files…")
        const context = await buildContext(files, controller.signal)
        if (context) params.set("context", context)
        const ingestible = files.filter((f) => !(f.type || "").startsWith("image/"))
        if (brain && brain !== "demo" && ingestible.length) {
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
            // honest failure: surface the server's error as a bot turn
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
            setStage(
              ev.stage === "start" ? "Searching the brain…" :
              ev.stage === "ready" ? "Composing the answer…" :
              ev.label || ev.stage,
            )
          }
        }
      }
    } catch (e) {
      const err = e as Error
      if (err.name !== "AbortError") {
        setTurns((t) => [...t, { role: "bot", text: "Could not reach the server: " + err.message }])
      }
      // Phase 9: persist the conversation server-side (single source of truth)
      const id = chatIdRef.current || (chatIdRef.current = crypto.randomUUID())
      const firstUser = turnsRef.current.find((t) => t.role === "user")
      void saveChat(id, firstUser ? firstUser.text : "Untitled", brain, turnsRef.current)
        .then((ok) => ok && refreshChats())
    } finally {
      setStreaming(false)
      setStage(null)
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
  }
  const openView = (v: "chat" | "connectors" | "graph") => {
    setView(v)
    const u = new URL(location.href)
    if (v === "chat") u.searchParams.delete("view")
    else u.searchParams.set("view", "connectors")
    history.pushState(null, "", u)
  }
  const handleBrainChange = (b: string) => {
    if (b === "__upload__") { setCreateOpen(true); return }
    if (b === "__graph__") {
      // Labeled legacy hand-off (no React graph yet) — documented in
      // UPGRADE_COMPLETION_REPORT; not a silent redirect.
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
    handleBrainChange(chatBrain)
    const u = new URL(location.href)
    u.searchParams.set("chat", id)
    history.pushState(null, "", u)
    setChatId(id)
    const serverTurns = await fetchChat(id)
    if (serverTurns.length) setTurns(serverTurns)
    else setTurns([])
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
            <div className="mt-6 flex max-w-[820px] flex-wrap justify-center gap-2.5">
              {CHIPS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => handleSend(c)}
                  className="rounded-full border border-border px-4 py-2 text-[13px] text-foreground/90 hover:border-primary hover:text-primary"
                >
                  {c}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto" aria-live="polite">
            <div ref={threadRef} className="mx-auto max-w-[780px] px-6 py-10">
              {turns.map((t, i) => (
                <div key={i} className={cn("group/turn mb-7", t.role === "user" && "flex justify-end")}>
                  <div
                    className={cn(
                      t.role === "user"
                        ? "max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-wash-2 px-4 py-2.5 text-[14px] leading-relaxed text-ink-2"
                        : "text-foreground/90",
                    )}
                  >
                    {t.role === "bot" ? (
                      <div className="max-w-none [&_a]:text-accent [&_a]:underline-offset-2 hover:[&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:border-accent/40 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground [&_code]:rounded [&_code]:bg-panel-2 [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[12.5px] [&_h2]:mb-2 [&_h2]:mt-5 [&_h2]:text-[15px] [&_h2]:font-semibold [&_h3]:mt-4 [&_h3]:text-[14px] [&_h3]:font-semibold [&_hr]:border-line [&_li]:my-1 [&_li]:marker:text-accent/70 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-3 [&_pre]:my-3 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:border [&_pre]:border-line [&_pre]:bg-panel-2 [&_pre]:p-3.5 [&_pre]:text-[12.5px] [&_pre]:leading-relaxed [&_strong]:text-ink [&_table]:my-3 [&_table]:w-full [&_table]:border-collapse [&_td]:border-b [&_td]:border-line [&_td]:px-2 [&_td]:py-1.5 [&_td]:text-[13px] [&_th]:border-b-2 [&_th]:border-line-2 [&_th]:px-2 [&_th]:py-1.5 [&_th]:text-left [&_th]:text-[10.5px] [&_th]:uppercase [&_th]:tracking-wide [&_th]:text-muted-foreground">
                        <Suspense fallback={<span className="whitespace-pre-wrap">{t.text}</span>}><Markdown>{t.text}</Markdown></Suspense>
                      </div>
                    ) : (
                      t.text
                    )}
                    {streaming && i === turns.length - 1 && t.role === "bot" && (
                      <span className="ml-0.5 inline-block h-3.5 w-[7px] translate-y-0.5 animate-pulse rounded-[2px] bg-accent/80" aria-hidden />
                    )}
                  </div>
                  {t.role === "bot" && t.sources && t.sources.length > 0 && (
                    <div className="mt-3">
                      <div className="mb-1.5 text-[10.5px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
                        Grounded in {t.sources.length} source{t.sources.length > 1 ? "s" : ""}
                      </div>
                      <div className="flex flex-wrap gap-1.5" aria-label="Cited sources">
                        {t.sources.map((s, si) => (
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
                  {t.role === "bot" && (
                    <div className="mt-2 flex items-center gap-1 opacity-0 transition-opacity duration-200 ease-out group-hover/turn:opacity-100">
                      <button
                        type="button"
                        aria-label="Copy answer"
                        title="Copy answer"
                        className="rounded-md p-1.5 text-muted-foreground transition-colors duration-150 ease-out hover:bg-wash hover:text-foreground"
                        onClick={() => navigator.clipboard.writeText(t.text)}
                      >
                        <Copy className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        aria-label="Regenerate answer"
                        title="Regenerate"
                        className="rounded-md p-1.5 text-muted-foreground transition-colors duration-150 ease-out hover:bg-wash hover:text-foreground"
                        onClick={() => {
                          const prev = turns[i - 1]
                          if (prev && prev.role === "user") {
                            setTurns((cur) => cur.slice(0, i - 1))
                            handleSend(prev.text)
                          }
                        }}
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                      </button>
                      <span className="px-1.5 text-[11px] text-muted-foreground/70">
                        {new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
                      </span>
                      <span className="ml-1 h-px flex-1 bg-line/60" aria-hidden />
                    </div>
                  )}
                </div>
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
      <Toaster position="bottom-right" />
    </div>
  )
}
