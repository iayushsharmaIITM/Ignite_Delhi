import { useCallback, useEffect, useRef, useState } from "react"
import { Sidebar } from "@/components/Sidebar"
import { PromptBox } from "@/components/PromptBox"
import { DEFAULT_BRAIN, greeting } from "@/lib/api"
import { cn } from "@/lib/utils"

type Turn = { role: "user" | "bot"; text: string }

const CHIPS = [
  "Summarise what is in this brain",
  "What are the next steps?",
  "Draft a mail from the latest answer",
  "Is everything consistent?",
]

export default function App() {
  const [collapsed, setCollapsed] = useState(
    localStorage.getItem("kestrel.sidebar.collapsed") === "1",
  )
  const [brain, setBrain] = useState(
    new URLSearchParams(location.search).get("brain") || DEFAULT_BRAIN,
  )
  const [turns, setTurns] = useState<Turn[]>([])
  const [streaming, setStreaming] = useState(false)
  const [input, setInput] = useState("")
  const threadRef = useRef<HTMLDivElement>(null)
  const [greet, setGreet] = useState(greeting)

  useEffect(() => {
    const t = setInterval(() => setGreet(greeting()), 60000)
    return () => clearInterval(t)
  }, [])

  const scrollBottom = () => {
    requestAnimationFrame(() =>
      threadRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }),
    )
  }

  const ask = useCallback(async (q: string) => {
    setTurns((t) => [...t, { role: "user", text: q }])
    setStreaming(true)
    ;(window as unknown as { CONTROLLER?: AbortController }).CONTROLLER = new AbortController()
    let text = ""
    try {
      const params = new URLSearchParams({ q })
      if (brain && brain !== "demo") params.set("dataset", brain)
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone
      params.set("tz", tz)
      params.set("local_time", new Date().toISOString())
      const res = await fetch(`/api/ask?${params}`, {
        signal: (window as unknown as { CONTROLLER?: AbortController }).CONTROLLER?.signal,
      })
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
          }
        }
      }
    } catch (e) {
      const err = e as Error
      if (err.name !== "AbortError") {
        setTurns((t) => [...t, { role: "bot", text: "Could not reach the server: " + err.message }])
      }
    } finally {
      setStreaming(false)
      scrollBottom()
    }
  }, [brain])

  const handleSend = (q: string) => {
    setInput(q)
    ask(q)
  }
  const handleStop = () => {
    ;(window as unknown as { CONTROLLER?: AbortController }).CONTROLLER?.abort()
  }
  const handleAttach = (files: FileList) => {
    // P6 connectors + extraction feed on the legacy path; the new UI wires
    // the same /api/extract route in the next step.
    alert(`Attached ${files.length} file(s) — extraction wiring lands in step 6.`)
  }
  const handleBrainChange = (b: string) => {
    if (b === "__upload__") { location.href = "/upload"; return }
    if (b === "__brains__") { location.href = "/brains"; return }
    if (b === "__graph__") { location.href = "/graph"; return }
    setBrain(b)
    const u = new URL(location.href)
    u.searchParams.set("brain", b)
    history.pushState(null, "", u)
  }
  const openChat = (chatId: string, chatBrain: string) => {
    handleBrainChange(chatBrain)
    const u = new URL(location.href)
    u.searchParams.set("chat", chatId)
    history.pushState(null, "", u)
  }
  const newChat = () => {
    const u = new URL(location.href)
    u.searchParams.delete("chat")
    u.searchParams.set("new", "1")
    history.pushState(null, "", u)
    setTurns([])
  }

  const hasInput = input.trim().length > 0

  return (
    <div className="flex h-full">
      <Sidebar
        collapsed={collapsed}
        onToggle={() => {
          setCollapsed((c) => {
            localStorage.setItem("kestrel.sidebar.collapsed", c ? "0" : "1")
            return !c
          })
        }}
        currentBrain={brain}
        currentChat={null}
        onBrainChange={handleBrainChange}
        onNewChat={newChat}
        onOpenChat={openChat}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        {turns.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center px-6 pb-10">
            <div
              aria-hidden
              className="mb-8 h-28 w-28 rotate-45 rounded-2xl bg-wash-2"
            />
            <h1 className="text-[30px] font-semibold tracking-tight text-foreground">{greet}</h1>
            <div className="mt-10 w-full max-w-[820px]">
              <PromptBox
                brain={brain}
                streaming={streaming}
                hasInput={hasInput}
                onSend={handleSend}
                onStop={handleStop}
                onAttach={handleAttach}
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
            <div ref={threadRef} className="mx-auto max-w-[820px] px-6 py-8">
              {turns.map((t, i) => (
                <div key={i} className={cn("mb-6", t.role === "user" && "flex justify-end")}>
                  <div
                    className={cn(
                      "whitespace-pre-wrap",
                      t.role === "user"
                        ? "max-w-[85%] rounded-2xl rounded-br-md border border-border bg-secondary px-4 py-3 text-foreground"
                        : "text-foreground/90",
                    )}
                  >
                    {t.text}
                  </div>
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
        {turns.length > 0 && (
          <div className="px-6 pb-6">
            <PromptBox
              brain={brain}
              streaming={streaming}
              hasInput={hasInput}
              onSend={handleSend}
              onStop={handleStop}
              onAttach={handleAttach}
            />
          </div>
        )}
      </main>
    </div>
  )
}
