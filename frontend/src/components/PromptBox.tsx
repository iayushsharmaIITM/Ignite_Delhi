import { useEffect, useRef, useState } from "react"
import { FileText, Send, Square, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"

type Props = {
  brain: string
  streaming: boolean
  hasInput: boolean
  stage?: string | null
  onSend: (q: string, files: File[]) => void
  onStop: () => void
}

export function PromptBox({ brain, streaming, hasInput, stage, onSend, onStop }: Props) {
  const [text, setText] = useState("")
  const [files, setFiles] = useState<File[]>([])
  const ref = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = Math.min(el.scrollHeight, 140) + "px"
  }, [text])

  const addFiles = (list: FileList | null) => {
    if (!list?.length) return
    setFiles((cur) => [...cur, ...Array.from(list)].slice(0, 6))
  }

  const submit = () => {
    if (streaming) {
      onStop()
      return
    }
    const q = text.trim()
    if (!q && files.length === 0) return
    onSend(q, files)
    setText("")
    setFiles([])
  }

  return (
    <div
      className={cn(
        "mx-auto w-full max-w-[820px] rounded-2xl border border-border bg-card shadow-lg transition-colors",
        dragging && "border-primary ring-2 ring-ring",
      )}
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        addFiles(e.dataTransfer.files)
      }}
    >
      <div className="flex items-center gap-2 px-4 pt-3">
        <button
          type="button"
          className="flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs text-foreground"
          aria-label={`Current brain: ${brain === "demo" ? "Demo brain" : brain}`}
        >
          <span className="grid h-3.5 w-3.5 place-items-center rounded-sm bg-primary text-[8px] text-primary-foreground">◆</span>
          {brain === "demo" ? "Demo brain" : brain}
        </button>
        <div className="ml-auto text-[11px] text-muted-foreground">{brain && `?brain=${brain}`}</div>
      </div>
      {files.length > 0 && (
        <ul className="flex flex-wrap gap-1.5 px-4 pt-2" aria-label="Attached files">
          {files.map((f, i) => (
            <li
              key={`${f.name}-${i}`}
              className="flex items-center gap-1.5 rounded-full border border-border bg-wash-3 py-1 pl-2.5 pr-1 text-[11.5px] text-foreground/90"
            >
              <FileText className="h-3 w-3 text-primary" aria-hidden />
              <span className="max-w-[180px] truncate">{f.name}</span>
              <button
                type="button"
                aria-label={`Remove ${f.name}`}
                className="rounded-full p-0.5 text-muted-foreground hover:bg-wash hover:text-foreground"
                onClick={() => setFiles((cur) => cur.filter((_, j) => j !== i))}
              >
                <X className="h-3 w-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <textarea
        ref={ref}
        rows={1}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault()
            submit()
          }
        }}
        placeholder="Ask across every document the company has written…"
        aria-label="Ask across every document"
        className="w-full resize-none bg-transparent px-4 py-3 text-[14.5px] text-foreground placeholder:text-muted-foreground focus:outline-none"
      />
      <div className="flex items-center px-3 pb-3">
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Attach files"
                className="h-8 w-8 text-muted-foreground"
                onClick={() => fileRef.current?.click()}
              >
                +
              </Button>
            </TooltipTrigger>
            <TooltipContent>Attach files</TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <input
          ref={fileRef}
          type="file"
          multiple
          hidden
          onChange={(e) => {
            addFiles(e.target.files)
            e.target.value = ""
          }}
        />
        {stage && streaming && (
          <span className="ml-2 truncate text-[11.5px] text-muted-foreground" role="status" aria-live="polite">
            {stage}
          </span>
        )}
        <div className="ml-auto">
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="icon"
                  aria-label={streaming ? "Stop generating" : "Send"}
                  onClick={submit}
                  className={cn(
                    "h-9 w-9 rounded-full",
                    streaming || hasInput || text.trim() || files.length
                      ? "bg-primary text-primary-foreground hover:bg-primary/90"
                      : "bg-panel-3 text-muted-foreground",
                  )}
                >
                  {streaming ? <Square className="h-3.5 w-3.5" /> : <Send className="h-4 w-4" />}
                </Button>
              </TooltipTrigger>
              <TooltipContent>{streaming ? "Stop generating" : "Send"}</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </div>
    </div>
  )
}
