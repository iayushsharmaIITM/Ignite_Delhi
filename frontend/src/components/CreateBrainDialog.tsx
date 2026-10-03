import { useRef, useState } from "react"
import { brainCreateV2Enabled, createBrainLegacy, createBrainV2, getJob, type JobStatus } from "@/lib/api"
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

type Props = {
  open: boolean
  onClose: (created?: string) => void
}

const HONEST_NOTE =
  "Ingestion runs on the free model route right now and can take several " +
  "minutes. You can keep chatting while the job finishes."

function newIdempotencyKey(): string {
  return `ui-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function CreateBrainDialog({ open, onClose }: Props) {
  const [name, setName] = useState("")
  const [files, setFiles] = useState<File[]>([])
  const [job, setJob] = useState<JobStatus | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  // Module scope: an idempotency key is not render state, and Date.now()/
  // Math.random() inside the component body trips the purity rule.
  const submit = async () => {
    setError(null)
    if (name.trim().length < 3 || files.length === 0) {
      setError("A brain needs a name (3+ characters) and at least one file.")
      return
    }
    setBusy(true)
    // Asked at submit, not at mount: `/api/brains/v2` is flag-gated and 404s
    // without the flag, so posting there unconditionally made this button dead on
    // every deployment that had not turned it on. The server says which path it
    // answers; there is nothing for the client to assume.
    const v2 = await brainCreateV2Enabled()
    if (v2) {
      const key = newIdempotencyKey()
      const r = await createBrainV2(name.trim(), files, key)
      setBusy(false)
      if (!r.ok || !r.job_id) {
        setError(r.detail || `Creation refused (HTTP ${r.status}).`)
        return
      }
      setJobId(r.job_id)
      poll(r.job_id)
      return
    }
    // No durable job path on this server: use the create route that answers,
    // which runs the ingestion inline and returns the outcome.
    const r = await createBrainLegacy(name.trim(), files)
    setBusy(false)
    if (!r.ok) {
      setError(r.detail || `Creation failed (HTTP ${r.status}).`)
      return
    }
    onClose(r.name || name.trim())
  }

  const poll = (id: string) => {
    const tick = async () => {
      const st = await getJob(id)
      if (st) {
        setJob(st)
        if (st.state === "SUCCEEDED") return
        if (st.state === "FAILED" || st.state === "RECONCILIATION_REQUIRED") return
      }
      setTimeout(tick, 5000)
    }
    tick()
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose(job && job.state === "SUCCEEDED" ? name : undefined)}>
      <DialogContent className="max-w-[440px] rounded-xl bg-card sm:rounded-xl">
        <DialogHeader>
          <DialogTitle className="text-foreground">Create a brain</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            Name it, attach documents, and Kestrel builds the brain from them —
            with verified sources. Ingestion takes a minute or two for a large
            upload.
          </DialogDescription>
        </DialogHeader>
        <div>
          <label htmlFor="brain-name" className="mb-1.5 block text-[10.5px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
            Name
          </label>
          <Input
            id="brain-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="brain-name (letters, numbers, underscores)"
            aria-label="Brain name"
            className="bg-panel-2"
          />
        </div>
        <div>
          <div className="mb-1.5 block text-[10.5px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
            Documents
          </div>
          <Button variant="secondary" className="w-full justify-start" onClick={() => fileRef.current?.click()}>
            {files.length ? `${files.length} file(s) attached` : "Attach documents…"}
          </Button>
        </div>
        <input ref={fileRef} id="brain-file-input" type="file" multiple hidden
               onChange={(e) => { setFiles(Array.from(e.target.files || [])); e.target.value = "" }} />
        {files.length > 0 && (
          <ul className="flex flex-wrap gap-1.5" aria-label="Attached files">
            {files.map((f, i) => (
              <li key={i} className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground">
                {f.name}
              </li>
            ))}
          </ul>
        )}
        {jobId && job && (
          <div className="rounded-lg border border-border bg-panel-2 p-3 text-xs" role="status" aria-live="polite">
            <div className="font-semibold text-foreground">
              Job {jobId.slice(0, 8)} —{" "}
              <span className={
                job.state === "SUCCEEDED" ? "text-ok" :
                job.state === "FAILED" ? "text-destructive" :
                job.state === "RECONCILIATION_REQUIRED" ? "text-warn" : "text-foreground"
              }>{job.state}</span>
            </div>
            {job.files?.map((f) => (
              <div key={f.client_file_id} className="mt-1 text-muted-foreground">
                {f.client_file_id.split(":").pop()}:{" "}
                <span className={
                  f.stage === "PROVENANCE_VERIFIED" ? "text-ok" :
                  f.stage === "FAILED" ? "text-destructive" : ""
                }>{f.stage}</span>
                {f.outcome ? ` — ${f.outcome}` : ""}
              </div>
            ))}
            <div className="mt-1.5 text-[10.5px] text-muted-foreground">{HONEST_NOTE}</div>
          </div>
        )}
        {error && <p className="text-xs text-destructive">{error}</p>}
        <Button
          className="w-full rounded-lg font-semibold"
          disabled={busy || !!jobId}
          onClick={submit}
        >
          {busy ? "Creating…" : jobId ? "Working…" : "Create brain"}
        </Button>
      </DialogContent>
    </Dialog>
  )
}
