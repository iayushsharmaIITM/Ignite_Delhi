import { useEffect, useState } from "react"

export type Brain = { name: string; chat_count?: number; is_demo?: boolean; is_system?: boolean }
export type ChatSummary = { id: string; title: string; brain: string; at: number }
export type Turn = {
  role: "user" | "bot"
  text: string
  sources?: { source: string; excerpt?: string }[]
  at?: number
}

export function useAuthHeaders() {
  const [headers, setHeaders] = useState<Record<string, string>>({})
  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((cfg) => {
        if (cfg.authMode !== "clerk") return
        // Clerk is mounted by the legacy shell script on this origin; use its
        // session when present, otherwise unauthenticated calls will 401.
        const w = window as unknown as {
          Clerk?: { session?: { getToken?: () => Promise<string> } }
        }
        w.Clerk?.session
          ?.getToken?.()
          .then((t) => t && setHeaders({ Authorization: `Bearer ${t}` }))
          .catch(() => {})
      })
      .catch(() => {})
  }, [])
  return headers
}

export function useBrains() {
  const [brains, setBrains] = useState<Brain[]>([])
  const refresh = () => {
    fetch("/api/brains")
      .then((r) => r.json())
      .then((d) =>
        setBrains(
          (d.brains || []).map((b: { name: string; is_demo?: boolean; is_system?: boolean }) => ({
            name: b.name,
            is_demo: b.is_demo,
            is_system: b.is_system,
          })),
        ),
      )
      .catch(() => {})
  }
  useEffect(refresh, [])
  return { brains, refreshBrains: refresh }
}

/* Phase 9: server-backed chat history (the single source of truth). */
export function useChats(brain: string | null) {
  const [chats, setChats] = useState<ChatSummary[]>([])
  const refresh = () => {
    if (!brain) return setChats([])
    fetch(`/api/chats?brain=${encodeURIComponent(brain)}`)
      .then((r) => r.json())
      .then((d) =>
        setChats(
          (d.chats || []).map((c: { id: string; title: string; brain: string; updated: string }) => ({
            id: c.id,
            title: c.title || "Untitled",
            brain: c.brain || brain,
            at: c.updated ? new Date(c.updated).getTime() : 0,
          })),
        ),
      )
      .catch(() => setChats([]))
  }
  useEffect(refresh, [brain])
  return { chats, refreshChats: refresh }
}

export async function fetchChat(id: string): Promise<Turn[]> {
  const r = await fetch(`/api/chats/${encodeURIComponent(id)}`)
  if (!r.ok) return []
  const d = await r.json()
  return (d.chat?.turns || []).map((t: { role: string; text: string; sources?: Turn["sources"] }) => ({
    role: t.role === "user" ? "user" : "bot",
    text: t.text || "",
    sources: t.sources || undefined,
  }))
}

export async function saveChat(id: string, title: string, brain: string, turns: Turn[]) {
  const r = await fetch(`/api/chats?brain=${encodeURIComponent(brain)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, title: title.slice(0, 120), turns }),
  })
  return r.ok
}

/* Phase 9: durable brain creation (v2 job path). */
export async function createBrainV2(
  name: string,
  files: File[],
  idempotencyKey: string,
): Promise<{ ok: boolean; job_id?: string; brain_id?: string; detail?: string; status?: number }> {
  const fd = new FormData()
  fd.append("name", name)
  fd.append("idempotency_key", idempotencyKey)
  files.forEach((f) => fd.append("files", f))
  const r = await fetch("/api/brains/v2", { method: "POST", body: fd })
  const d = await r.json().catch(() => ({}))
  return { ok: r.status === 202, job_id: d.job_id, brain_id: d.brain_id, detail: d.detail, status: r.status }
}

export type JobStatus = {
  state: string
  error_code?: string | null
  files?: { client_file_id: string; stage: string; outcome?: string | null }[]
}

export async function getJob(jobId: string): Promise<JobStatus | null> {
  const r = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`)
  if (!r.ok) return null
  const d = await r.json()
  return { state: d.job.state, error_code: d.job.error_code, files: d.files }
}

export function greeting(): string {
  const h = new Date().getHours()
  return h < 12 ? "Morning, how can I help?" : h < 17 ? "Afternoon, how can I help?" : "Evening, how can I help?"
}

export const DEFAULT_BRAIN = "company_brain"
