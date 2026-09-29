import { useEffect, useRef, useState } from "react"
import { Send, Square } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"

type Props = {
  brain: string
  streaming: boolean
  hasInput: boolean
  onSend: (q: string) => void
  onStop: () => void
  onAttach: (files: FileList) => void
}

export function PromptBox({ brain, streaming, hasInput, onSend, onStop, onAttach }: Props) {
  const [text, setText] = useState("")
  const ref = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = Math.min(el.scrollHeight, 140) + "px"
  }, [text])

  const submit = () => {
    const q = text.trim()
    if (!q) return
    if (streaming) {
      onStop()
      return
    }
    onSend(q)
    setText("")
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
        if (e.dataTransfer.files?.length) onAttach(e.dataTransfer.files)
      }}
    >
      <div className="flex items-center gap-2 px-4 pt-3">
        <button
          type="button"
          className="flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs text-foreground"
          aria-label="Current brain"
        >
          <span className="grid h-3.5 w-3.5 place-items-center rounded-sm bg-primary text-[8px] text-primary-foreground">◆</span>
          {brain === "demo" ? "Demo brain" : brain}
        </button>
        <div className="ml-auto text-[11px] text-muted-foreground">{brain && `?brain=${brain}`}</div>
      </div>
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
          onChange={(e) => e.target.files && onAttach(e.target.files)}
        />
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
                    streaming || hasInput || text.trim()
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
