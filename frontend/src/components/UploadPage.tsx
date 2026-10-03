import { useCallback, useEffect, useRef, useState } from "react"
import {
  AlertTriangle,
  CheckCircle2,
  CloudUpload,
  ExternalLink,
  FileText,
  Loader2,
  Plus,
  X,
} from "lucide-react"
import { apiFetch } from "@/lib/api"
import { t } from "@/lib/i18n"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */

const MAX_BYTES = 5 * 1024 * 1024 // 5 MB per file
const MAX_FILES = 40
const LOG_CAP = 60

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

type FileStatus = "ok" | "bad" | "warn"

type FileEntry = {
  file: File
  status?: FileStatus
  message?: string
}

type LogLine = {
  text: string
  status?: FileStatus
}

type PipelineEvent = {
  stage: string
  state?: string
  detail?: string
  message?: string
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function humanBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1048576).toFixed(1)} MB`
}

function isValidBrainName(name: string): boolean {
  return /^[a-zA-Z0-9_]{3,40}$/.test(name)
}

/* ------------------------------------------------------------------ */
/* UploadPage                                                          */
/* ------------------------------------------------------------------ */

export function UploadPage() {
  const [name, setName] = useState("")
  const [files, setFiles] = useState<FileEntry[]>([])
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [log, setLog] = useState<LogLine[]>([])
  const [done, setDone] = useState<{ ok: boolean; brain: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [appendMode, setAppendMode] = useState(false)
  const [offerAppend, setOfferAppend] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const logRef = useRef<HTMLUListElement>(null)

  /* Prefill from ?brain= query param */
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const brain = params.get("brain")
    if (brain) {
      setName(brain)
      setAppendMode(true)
      addLog(
        `Adding to the existing brain "${brain}". Its current graph stays; these documents are added to it.`,
        "warn",
      )
    }
  }, [])

  /* Auto-scroll log */
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [log])

  const addLog = useCallback((text: string, status?: FileStatus) => {
    setLog((prev) => {
      const next = [...prev, { text, status }]
      return next.length > LOG_CAP ? next.slice(next.length - LOG_CAP) : next
    })
  }, [])

  const addFiles = useCallback(
    (incoming: FileList | File[]) => {
      const arr = Array.from(incoming)
      setFiles((prev) => {
        let next = [...prev]
        for (const f of arr) {
          if (next.length >= MAX_FILES) {
            addLog(`Only the first ${MAX_FILES} files are used.`, "warn")
            break
          }
          if (f.size > MAX_BYTES) {
            addLog(`${f.name} is ${humanBytes(f.size)} — over the 5 MB limit.`, "bad")
            continue
          }
          if (next.some((e) => e.file.name === f.name && e.file.size === f.size)) continue
          next.push({ file: f })
        }
        return next
      })
    },
    [addLog],
  )

  const removeFile = useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }, [])

  const canBuild = name.trim().length >= 3 && files.length > 0 && !busy

  /* ---------------------------------------------------------------- */
  /* Submit + stream                                                 */
  /* ---------------------------------------------------------------- */

  const submit = useCallback(
    async (append: boolean) => {
      const trimmed = name.trim()
      if (!trimmed || files.length === 0) return

      setBusy(true)
      setError(null)
      setDone(null)
      setOfferAppend(false)
      setLog([])

      const fd = new FormData()
      fd.append("name", trimmed)
      if (append) fd.append("append", "true")
      files.forEach((e) => fd.append("files", e.file, e.file.name))

      try {
        const res = await apiFetch("/api/brains", { method: "POST", body: fd })
        const body = await res.json().catch(() => ({}))

        if (res.status === 409 && !append) {
          addLog(
            `"${trimmed}" already exists. Add these files to it, or change the name.`,
            "warn",
          )
          setOfferAppend(true)
          setBusy(false)
          return
        }

        if (!res.ok) {
          throw new Error(body.detail || `HTTP ${res.status}`)
        }

        /* Success — show per-file results */
        if (body.partial) {
          addLog(
            `Brain "${body.name}" created, but only ${body.documents} document(s) were stored (${body.chars?.toLocaleString() ?? 0} characters). Failures are listed below.`,
            "warn",
          )
        } else {
          addLog(
            `Brain "${body.name}" created with ${body.documents} document(s), ${body.chars?.toLocaleString() ?? 0} characters.`,
            "ok",
          )
        }

        for (const s of body.skipped || []) {
          addLog(`skipped ${s.name} — ${s.error}`, "bad")
        }
        for (const r of body.ingested || []) {
          if (r.ok === false) addLog(`failed to store ${r.name} — ${r.error || "unknown"}`, "bad")
        }

        /* Stream pipeline events */
        await streamEvents(body.name)
      } catch (e) {
        const msg = (e as Error).message
        addLog(`Could not create the brain: ${msg}`, "bad")
        setError(msg)
        setBusy(false)
      }
    },
    [name, files, addLog],
  )

  const streamEvents = useCallback(
    async (brainName: string) => {
      addLog("Waiting for the graph to build — this is the slow part (~1 min)…")

      let finished = false
      const finish = (ok: boolean) => {
        if (finished) return
        finished = true
        setBusy(false)
        setDone({ ok, brain: brainName })
      }

      try {
        const res = await apiFetch(
          `/api/brains/${encodeURIComponent(brainName)}/events`,
        )
        if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

        const reader = res.body.getReader()
        const dec = new TextDecoder()
        let buf = ""

        while (true) {
          const { value, done } = await reader.read()
          if (done) break
          buf += dec.decode(value, { stream: true })
          const lines = buf.split("\n")
          buf = lines.pop() || ""

          for (const line of lines) {
            if (!line.trim()) continue
            let m: PipelineEvent
            try {
              m = JSON.parse(line)
            } catch {
              continue
            }

            if (m.stage === "poll") {
              addLog(String(m.state || "working"))
            } else if (m.stage === "ready") {
              addLog("Pipeline complete.", "ok")
              finish(true)
            } else if (m.stage === "failed") {
              addLog(`Ingestion failed: ${m.detail || "no reason given"}`, "bad")
              finish(false)
            } else if (m.stage === "error") {
              addLog(`Error: ${m.message}`, "bad")
              finish(false)
            } else if (m.stage === "timeout") {
              addLog("Timed out waiting. Check the brains page.", "warn")
              finish(false)
            }
          }
        }

        /* Handle final line without newline */
        if (buf.trim()) {
          let m: PipelineEvent | null
          try {
            m = JSON.parse(buf)
          } catch {
            m = null
          }
          if (m) {
            if (m.stage === "ready") {
              addLog("Pipeline complete.", "ok")
              finish(true)
            } else if (m.stage === "failed") {
              addLog(`Ingestion failed: ${m.detail || "no reason given"}`, "bad")
              finish(false)
            } else if (m.stage === "timeout") {
              addLog("Timed out waiting.", "warn")
              finish(false)
            }
          }
        }
      } catch (e) {
        addLog(`Progress stream failed: ${(e as Error).message}`, "warn")
      }
      finish(false)
    },
    [addLog],
  )

  /* ---------------------------------------------------------------- */
  /* Drag handlers                                                    */
  /* ---------------------------------------------------------------- */

  const onDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(true)
  }, [])

  const onDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
  }, [])

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
  }, [])

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      addFiles(e.dataTransfer.files)
    },
    [addFiles],
  )

  /* ---------------------------------------------------------------- */
  /* Render                                                           */
  /* ---------------------------------------------------------------- */

  const nameValid = isValidBrainName(name.trim())
  const showNameHint = name.trim().length > 0 && !nameValid

  return (
    <div className="flex-1 overflow-y-auto" aria-label="Upload">
      <div className="mx-auto max-w-[720px] px-6 py-10">
        {/* Header */}
        <h1 className="text-[22px] font-semibold tracking-tight text-foreground">
          {t("up.h1")}
        </h1>
        <p className="mt-1 text-[13.5px] text-muted-foreground">{t("up.sub")}</p>

        {/* Brain name */}
        <section className="mt-8">
          <label
            htmlFor="brain-name"
            className="mb-1.5 block text-[10.5px] font-medium uppercase tracking-[0.08em] text-muted-foreground"
          >
            {t("up.label_name")}
          </label>
          <Input
            id="brain-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("up.name_ph")}
            aria-label={t("up.label_name")}
            className="bg-panel-2 font-mono"
            disabled={appendMode}
          />
          {showNameHint && (
            <p className="mt-1.5 text-[12px] text-warn">{t("up.name_hint")}</p>
          )}
          {appendMode && (
            <p className="mt-1.5 flex items-center gap-1.5 text-[12px] text-warn">
              <AlertTriangle className="h-3.5 w-3.5" />
              Adding to existing brain — files will be appended.
            </p>
          )}
        </section>

        {/* Drop zone */}
        <section className="mt-6">
          <div className="mb-1.5 block text-[10.5px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
            {t("up.label_docs")}
          </div>
          <div
            role="button"
            tabIndex={0}
            aria-label="Drop files here or choose files"
            className={cn(
              "flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed border-border bg-card px-6 py-10 text-center transition-colors duration-150 ease-out",
              dragging && "border-accent bg-accent-dim",
            )}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click() }}
            onDragEnter={onDragEnter}
            onDragLeave={onDragLeave}
            onDragOver={onDragOver}
            onDrop={onDrop}
          >
            <CloudUpload className={cn("h-8 w-8", dragging ? "text-accent" : "text-muted-foreground")} />
            <p className="text-[14px] font-medium text-foreground">{t("up.drop")}</p>
            <p className="text-[12.5px] text-muted-foreground">
              or{" "}
              <button
                type="button"
                className="text-accent underline"
                onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click() }}
              >
                {t("up.choose")}
              </button>
            </p>
            <p className="mt-1 text-[11.5px] text-muted-foreground/70">{t("up.hint")}</p>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            hidden
            onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = "" }}
          />
        </section>

        {/* File list */}
        {files.length > 0 && (
          <ul className="mt-3 flex flex-col gap-1.5" aria-label="Selected files">
            {files.map((entry, i) => (
              <li
                key={`${entry.file.name}-${i}`}
                className="flex items-center gap-3 rounded-lg border border-border bg-panel-2 px-3 py-2"
              >
                <FileText className="h-4 w-4 flex-none text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate font-mono text-[12.5px] text-foreground">
                  {entry.file.name}
                </span>
                {entry.status && (
                  <Badge
                    variant={entry.status === "ok" ? "default" : entry.status === "bad" ? "destructive" : "secondary"}
                    className="text-[10px]"
                  >
                    {entry.status}
                  </Badge>
                )}
                <span className="flex-none text-[11.5px] text-muted-foreground">
                  {humanBytes(entry.file.size)}
                </span>
                <button
                  type="button"
                  aria-label={`Remove ${entry.file.name}`}
                  className="flex-none rounded p-0.5 text-muted-foreground transition-colors hover:text-destructive"
                  onClick={() => removeFile(i)}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}

        {/* Build button */}
        <div className="mt-6 flex items-center gap-3">
          <Button
            className="rounded-lg font-semibold"
            disabled={!canBuild}
            onClick={() => submit(false)}
          >
            {busy ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Working…
              </>
            ) : (
              t("up.build")
            )}
          </Button>
          {offerAppend && !busy && (
            <Button
              variant="secondary"
              className="rounded-lg"
              onClick={() => submit(true)}
            >
              <Plus className="h-4 w-4" />
              Add to &quot;{name.trim()}&quot;
            </Button>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="mt-4 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-[13px] text-destructive" role="alert">
            {error}
          </div>
        )}

        {/* Ingestion log */}
        {log.length > 0 && (
          <section className="mt-8">
            <div className="mb-2 text-[10.5px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
              {t("up.label_ing")}
            </div>
            <ul
              ref={logRef}
              className="flex max-h-[320px] flex-col gap-1 overflow-y-auto rounded-lg border border-border bg-panel-2 p-2 font-mono text-[12px]"
              aria-label="Ingestion log"
              aria-live="polite"
            >
              {log.map((line, i) => (
                <li
                  key={i}
                  className={cn(
                    "rounded px-2 py-1",
                    line.status === "ok" && "text-ok",
                    line.status === "bad" && "text-destructive",
                    line.status === "warn" && "text-warn",
                    !line.status && "text-muted-foreground",
                  )}
                >
                  {line.text}
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Done state */}
        {done && (
          <div
            className={cn(
              "mt-6 rounded-xl border p-4",
              done.ok
                ? "border-ok/30 bg-ok-dim"
                : "border-destructive/30 bg-destructive/10",
            )}
            role="status"
          >
            {done.ok ? (
              <div className="flex items-start gap-3">
                <CheckCircle2 className="mt-0.5 h-5 w-5 flex-none text-ok" />
                <div>
                  <p className="text-[14px] font-semibold text-foreground">Ready.</p>
                  <a
                    href={`/?brain=${encodeURIComponent(done.brain)}`}
                    className="mt-1 inline-flex items-center gap-1 text-[13px] text-accent hover:underline"
                  >
                    Open the dashboard for {done.brain}
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              </div>
            ) : (
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-5 w-5 flex-none text-destructive" />
                <p className="text-[13px] text-foreground">
                  Ingestion did not finish cleanly. The brain may still be usable — check the brains page.
                </p>
              </div>
            )}
          </div>
        )}

        {/* Footer */}
        <footer className="mt-10 flex flex-wrap gap-4 border-t border-border pt-5 text-[12px] text-muted-foreground">
          <a href="/" className="text-accent hover:underline">
            demo dashboard
          </a>
          <a href="/brains" className="text-accent hover:underline">
            all brains
          </a>
          <a href="/health" className="text-accent hover:underline">
            /health
          </a>
        </footer>
      </div>
    </div>
  )
}
