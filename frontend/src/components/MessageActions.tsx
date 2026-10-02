import { useState } from "react"
import {
  Copy,
  Check,
  Mail,
  ListTodo,
  MessageSquareText,
  ThumbsUp,
  ThumbsDown,
  RotateCcw,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { t } from "@/lib/i18n"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"


type Props = {
  text: string
  onRegenerate: () => void
}

export function MessageActions({ text, onRegenerate }: Props) {
  const [copied, setCopied] = useState(false)
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null)
  const [emailOpen, setEmailOpen] = useState(false)
  const [stepsOpen, setStepsOpen] = useState(false)
  const [chatUpdateOpen, setChatUpdateOpen] = useState(false)

  const timestamp = new Date().toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  })

  const handleCopy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleThumbs = (dir: "up" | "down") => {
    setFeedback(dir)
    setTimeout(() => setFeedback(null), 2000)
  }

  return (
    <div className="mt-2 flex items-center gap-1 opacity-0 transition-opacity duration-200 ease-out group-hover/turn:opacity-100">
      {/* Copy */}
      <button
        type="button"
        aria-label={t("action.copy")}
        title={t("action.copy")}
        className="rounded-md p-1.5 text-muted-foreground transition-colors duration-150 ease-out hover:bg-wash hover:text-foreground"
        onClick={handleCopy}
      >
        {copied ? (
          <Check className="h-3.5 w-3.5 text-ok" />
        ) : (
          <Copy className="h-3.5 w-3.5" />
        )}
      </button>

      {/* Email draft */}
      <button
        type="button"
        aria-label={t("action.email")}
        title={t("action.email")}
        className="rounded-md p-1.5 text-muted-foreground transition-colors duration-150 ease-out hover:bg-wash hover:text-foreground"
        onClick={() => setEmailOpen(true)}
      >
        <Mail className="h-3.5 w-3.5" />
      </button>

      {/* Next steps */}
      <button
        type="button"
        aria-label={t("action.steps")}
        title={t("action.steps")}
        className="rounded-md p-1.5 text-muted-foreground transition-colors duration-150 ease-out hover:bg-wash hover:text-foreground"
        onClick={() => setStepsOpen(true)}
      >
        <ListTodo className="h-3.5 w-3.5" />
      </button>

      {/* Chat update */}
      <button
        type="button"
        aria-label={t("action.chat_update")}
        title={t("action.chat_update")}
        className="rounded-md p-1.5 text-muted-foreground transition-colors duration-150 ease-out hover:bg-wash hover:text-foreground"
        onClick={() => setChatUpdateOpen(true)}
      >
        <MessageSquareText className="h-3.5 w-3.5" />
      </button>

      {/* Thumbs up */}
      <button
        type="button"
        aria-label={t("action.thumbs_up")}
        title={t("action.thumbs_up")}
        className={cn(
          "rounded-md p-1.5 transition-colors duration-150 ease-out hover:bg-wash",
          feedback === "up"
            ? "text-ok"
            : "text-muted-foreground hover:text-foreground",
        )}
        onClick={() => handleThumbs("up")}
      >
        <ThumbsUp className="h-3.5 w-3.5" />
      </button>

      {/* Thumbs down */}
      <button
        type="button"
        aria-label={t("action.thumbs_down")}
        title={t("action.thumbs_down")}
        className={cn(
          "rounded-md p-1.5 transition-colors duration-150 ease-out hover:bg-wash",
          feedback === "down"
            ? "text-bad"
            : "text-muted-foreground hover:text-foreground",
        )}
        onClick={() => handleThumbs("down")}
      >
        <ThumbsDown className="h-3.5 w-3.5" />
      </button>

      {/* Regenerate */}
      <button
        type="button"
        aria-label={t("action.regenerate")}
        title={t("action.regenerate")}
        className="rounded-md p-1.5 text-muted-foreground transition-colors duration-150 ease-out hover:bg-wash hover:text-foreground"
        onClick={onRegenerate}
      >
        <RotateCcw className="h-3.5 w-3.5" />
      </button>

      {/* Timestamp */}
      <span className="px-1.5 text-[11px] text-muted-foreground/70">
        {timestamp}
      </span>

      <span className="ml-1 h-px flex-1 bg-line/60" aria-hidden />

      {/* Email draft modal */}
      <Dialog open={emailOpen} onOpenChange={setEmailOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("email.title")}</DialogTitle>
            <DialogDescription>{t("email.body")}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                {t("email.to")}
              </label>
              <input
                type="email"
                placeholder="colleague@company.com"
                className="w-full rounded-md border border-line-2 bg-panel-2 px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:border-accent/60 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                {t("email.subject")}
              </label>
              <input
                type="text"
                placeholder="Re: Kestrel answer"
                className="w-full rounded-md border border-line-2 bg-panel-2 px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:border-accent/60 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                {t("email.body")}
              </label>
              <textarea
                readOnly
                value={text}
                rows={8}
                className="w-full resize-none rounded-md border border-line-2 bg-panel-2 px-3 py-2 text-sm text-foreground/90 focus:outline-none"
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setEmailOpen(false)}
            >
              {t("common.close")}
            </Button>
            <Button
              size="sm"
              onClick={() => {
                navigator.clipboard.writeText(text)
                setEmailOpen(false)
              }}
            >
              {t("email.copy")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Next steps modal */}
      <Dialog open={stepsOpen} onOpenChange={setStepsOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("steps.title")}</DialogTitle>
            <DialogDescription>{t("steps.body")}</DialogDescription>
          </DialogHeader>
          <div className="rounded-lg border border-line bg-panel-2 p-4">
            <p className="text-sm text-muted-foreground">
              {text.slice(0, 500)}
              {text.length > 500 ? "…" : ""}
            </p>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setStepsOpen(false)}
            >
              {t("common.close")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Chat update modal */}
      <Dialog open={chatUpdateOpen} onOpenChange={setChatUpdateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("chat_update.title")}</DialogTitle>
            <DialogDescription>{t("chat_update.body")}</DialogDescription>
          </DialogHeader>
          <textarea
            readOnly
            value={text}
            rows={8}
            className="w-full resize-none rounded-md border border-line-2 bg-panel-2 px-3 py-2 text-sm text-foreground/90 focus:outline-none"
          />
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setChatUpdateOpen(false)}
            >
              {t("common.close")}
            </Button>
            <Button
              size="sm"
              onClick={() => {
                navigator.clipboard.writeText(text)
                setChatUpdateOpen(false)
              }}
            >
              {t("common.copy")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
