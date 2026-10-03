import { useRef, useState } from "react"
import { useAuthHeaders } from "@/lib/api"
import { t } from "@/lib/i18n"

type Props = {
  open: boolean
  brain: string
  onClose: () => void
  onAdded?: () => void
}

type Row = { name: string; size: number; file?: File; status?: "ok" | "bad"; st?: string }
type Note = { text: string; cls: string }

// Legacy #files-sheet (static/index.html openFilesSheet/addPicked/filesGo):
// add documents to the CURRENT brain, with per-file verdicts and the real
// pipeline progress streamed from /api/brains/<name>/events. The demo brain
// is read-only and says so.
const SUPPORTED = /\.(txt|md|csv|json|pdf|docx|py|js|ts|jsx|tsx|java|go|rs|c|cpp|h|hpp|sh|sql|yaml|yml|toml|ini|cfg|html|css)$/i
const MAX_BYTES = 5 * 1024 * 1024
const MAX_FILES = 40

export function FilesSheet({ open, brain, onClose, onAdded }: Props) {
  const [picked, setPicked] = useState<Row[]>([])
  const [notes, setNotes] = useState<Note[]>([])
  const [pipeline, setPipeline] = useState("")
  const [done, setDone] = useState("")
  const [busy, setBusy] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const authHeaders = useAuthHeaders()
  const addPicked = (list: FileList | null) => {
    if (!list?.length) return
    const next: Row[] = [...picked]
    const newNotes: Note[] = []
    for (const f of Array.from(list)) {
      if (next.length >= MAX_FILES) { newNotes.push({ text: `Only the first ${MAX_FILES} files are used.`, cls: "warn" }); break }
      if (f.size > MAX_BYTES) { newNotes.push({ text: f.name + " is over the 5 MB limit.", cls: "bad" }); continue }
      if (!SUPPORTED.test(f.name)) { newNotes.push({ text: f.name + " — unsupported format.", cls: "bad" }); continue }
      if (next.some((p) => p.name === f.name && p.size === f.size)) continue
      next.push({ name: f.name, size: f.size, file: f })
    }
    setPicked(next)
    setNotes(newNotes)
  }

  const upload = async () => {
    if (!picked.length || !brain || busy) return
    setBusy(true)
    setDone("")
    setPipeline(`uploading ${picked.length} file(s)…`)
    const fd = new FormData()
    fd.append("name", brain)
    fd.append("append", "true")
    picked.forEach((p) => {
      const f = p.file
      if (f) fd.append("files", f)
    })
    try {
      const res = await fetch("/api/brains", { method: "POST", body: fd, headers: authHeaders })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        // The API's own refusal messages are the honest ones — surface verbatim.
        setPipeline("")
        setDone(data.detail || `HTTP ${res.status}`)
        setBusy(false)
        return
      }
      setPicked((rows) =>
        rows.map((r) => {
          const verdict = (data.ingested || []).find((x: { name: string }) => x.name === r.name)
          return verdict
            ? { ...r, status: verdict.ok ? ("ok" as const) : ("bad" as const), st: verdict.ok ? "added" : verdict.error || "failed" }
            : r
        }),
      )
      setNotes((data.skipped || []).map((r: { name: string; error?: string }) => ({
        text: r.name + " — " + (r.error || "skipped"), cls: "bad",
      })))
      if (data.ok || data.partial) {
        setPipeline("building the knowledge graph…")
        await streamPipeline(brain, setPipeline)
        setDone(
          (data.appended ? `Added to “${brain}”` : `Brain “${brain}” updated`) +
            ` — ${data.documents} document(s) in this brain. Ask away.`,
        )
        setPicked([])
        onAdded?.()
      } else {
        setPipeline("")
        setDone("None of the files could be ingested.")
      }
    } catch (err) {
      setPipeline("")
      setDone("Could not reach the server: " + (err as Error).message)
    }
    setBusy(false)
  }

  // Same NDJSON shape as /api/ask; reflects real pipeline states until the
  // dataset reaches a terminal one (or the sheet closes).
  const streamPipeline = async (name: string, set: (s: string) => void) => {
    try {
      const res = await fetch(`/api/brains/${encodeURIComponent(name)}/events?timeout_s=600`, {
        headers: authHeaders,
      })
      const reader = res.body!.getReader()
      const dec = new TextDecoder()
      let buf = ""
      outer: while (true) {
        const { value, done: finished } = await reader.read()
        if (finished) break
        buf += dec.decode(value, { stream: true })
        const lines = buf.split("\n")
        buf = lines.pop() || ""
        for (const line of lines) {
          if (!line.trim()) continue
          let ev: { stage?: string; state?: string; detail?: string; message?: string }
          try { ev = JSON.parse(line) } catch { continue }
          if (ev.stage === "poll") set(ev.state || "processing…")
          else if (ev.stage === "ready") { set("pipeline complete ✓"); break outer }
          else if (ev.stage === "failed") { set("pipeline failed: " + (ev.detail || "")); break outer }
          else if (ev.stage === "timeout") { set("still building — check back in a minute."); break outer }
          else if (ev.stage === "error") { set("error: " + ev.message); break outer }
        }
      }
    } catch { /* sheet closed or network dropped — the pipeline continues server-side */ }
  }

  return (
    <div
      id="files-sheet"
      hidden={!open}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="sheet">
        <div className="head">
          <strong>{t("files.title", "Add documents")}</strong>
          <span className="where" id="files-target">{brain ? `into ${brain}` : "into the demo brain (read-only)"}</span>
          <span className="sp">
            <button type="button" id="files-close" onClick={onClose}>{t("files.close", "Close")}</button>
          </span>
        </div>
        <div className="body">
          <div className="notice" id="files-notice" hidden={!!brain}>
            The demo brain is read-only. Create a brain from "New brain" (sidebar), then add files from its chat.
          </div>
          <div
            className="drop"
            id="drop2"
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add("over") }}
            onDragEnter={(e) => { e.preventDefault(); e.currentTarget.classList.add("over") }}
            onDragLeave={(e) => { e.preventDefault(); e.currentTarget.classList.remove("over") }}
            onDrop={(e) => { e.preventDefault(); e.currentTarget.classList.remove("over"); addPicked(e.dataTransfer.files) }}
          >
            <span>{t("files.drop", "Drop files here or choose files")}</span>
            <div className="hint">{t("files.hint", "PDF, DOCX, TXT, MD, CSV, JSON, code files · up to 5 MB each · 40 max. Added straight into this brain — no restart, immediately answerable.")}</div>
          </div>
          <input ref={inputRef} type="file" id="file-input" multiple hidden
                 onChange={(e) => { addPicked(e.target.files); e.target.value = "" }} />
          <ul className="files" id="filelist">
            {picked.map((r) => (
              <li key={r.name + r.size} className={r.status}>
                <span>{r.name}</span>
                <span className="st">{r.st ?? ((r.size / 1024).toFixed(0) + " KB")}</span>
              </li>
            ))}
            {notes.map((n, i) => (
              <li key={"note" + i} className={n.cls}>
                <span className="st">{n.text}</span>
              </li>
            ))}
          </ul>
          <div className="pipeline" id="pipeline">{pipeline}</div>
          <div className="done" id="files-done">{done}</div>
          <div className="cta">
            <button type="button" id="files-go" disabled={!picked.length || !brain || busy} onClick={upload}>
              {t("files.add", "Add to brain")}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
