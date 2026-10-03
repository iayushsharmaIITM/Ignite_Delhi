import { useEffect, useState } from "react"
import { awaitClerkBoot, getClerkToken } from "@/lib/clerk"

export type Brain = { name: string; chat_count?: number; is_demo?: boolean; is_system?: boolean }
export type ChatSummary = { id: string; title: string; brain: string; at: number }
export type Turn = {
  role: "user" | "bot"
  text: string
  sources?: { source: string; excerpt?: string }[]
  at?: number
  /** Legacy .bubble.err: the turn is a failure state, not model output. */
  error?: boolean
}

/* ==========================================================================
 * ONE authenticated transport.
 *
 * The legacy shell put every call through KestrelAuth.authHeaders(), which
 * awaits Clerk boot and mints a token PER REQUEST (static/auth.js:73). The
 * port had a mount-time hook instead, used in three places — so on the live
 * stack (`.env`: AUTH_MODE=clerk) /api/ask, /api/chats, /api/brains,
 * /api/source, /api/extract, /api/graph, /api/actions/* and /api/connectors/*
 * all went out unauthenticated and 401'd, which the UI then rendered as empty
 * data ("No saved chats yet").
 *
 * So: every call in src/ goes through apiFetch. It is a function, not a hook,
 * because the ask path and the persist path are not components.
 * ========================================================================== */

export type ApiConfig = { authMode?: string; publishableKey?: string }

let configPromise: Promise<ApiConfig> | null = null

/** /api/config, fetched once per page load (App.tsx and the transport share it). */
export function apiConfig(): Promise<ApiConfig> {
  if (!configPromise) {
    configPromise = fetch("/api/config")
      .then((r) => r.json())
      .catch(() => ({}) as ApiConfig)
  }
  return configPromise
}

/** Authorization for the configured auth mode — {} when auth is off. */
export async function authHeaders(): Promise<Record<string, string>> {
  const cfg = await apiConfig()
  if (cfg.authMode !== "clerk") return {}
  await awaitClerkBoot()
  const token = await getClerkToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/**
 * fetch() with the caller's credentials attached, retrying once on 401 with a
 * freshly minted token.
 *
 * The retry matters: Clerk session tokens are short-lived (~60s), so a page
 * left open across an expiry sends a token that was valid when it was read and
 * stale by the time the request lands. One forced refresh is the difference
 * between "the app stops working if you leave it open" and not.
 */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const auth = await authHeaders()
  for (const [k, v] of Object.entries(auth)) headers.set(k, v)

  const res = await fetch(path, { ...init, headers })
  if (res.status !== 401) return res

  const cfg = await apiConfig()
  if (cfg.authMode !== "clerk") return res
  const fresh = await getClerkToken({ skipCache: true })
  if (!fresh) return res
  const retryHeaders = new Headers(init.headers)
  retryHeaders.set("Authorization", `Bearer ${fresh}`)
  return fetch(path, { ...init, headers: retryHeaders })
}

/**
 * The server's own refusal message, verbatim.
 *
 * The port's policy is that honest states quote the server (the draft box
 * already does: App.tsx draftFrom). A 401 body is `{"detail": "A valid Clerk
 * session token is required."}` — showing that beats showing nothing.
 */
export async function serverError(res: Response): Promise<string> {
  const d = await res.json().catch(() => null)
  const detail = d && (d.detail || d.error)
  return typeof detail === "string" && detail ? detail : `HTTP ${res.status}`
}

/* ==========================================================================
 * Reads
 * ========================================================================== */

export function useBrains() {
  const [brains, setBrains] = useState<Brain[]>([])
  const [brainsError, setBrainsError] = useState<string | null>(null)
  const refresh = () => {
    apiFetch("/api/brains")
      .then(async (r) => {
        if (!r.ok) throw new Error(await serverError(r))
        return r.json()
      })
      .then((d) => {
        setBrains(
          (d.brains || []).map((b: { name: string; is_demo?: boolean; is_system?: boolean }) => ({
            name: b.name,
            is_demo: b.is_demo,
            is_system: b.is_system,
          })),
        )
        setBrainsError(null)
      })
      // Never swallow: an unauthenticated read used to render as "no brains".
      .catch((e) => {
        setBrains([])
        setBrainsError((e as Error).message)
      })
  }
  useEffect(refresh, [])
  return { brains, refreshBrains: refresh, brainsError }
}

/* Phase 9: server-backed chat history (the single source of truth). */
export function useChats(brain: string | null) {
  const [chats, setChats] = useState<ChatSummary[]>([])
  const [chatsError, setChatsError] = useState<string | null>(null)
  const refresh = () => {
    if (!brain) {
      setChats([])
      setChatsError(null)
      return
    }
    apiFetch(`/api/chats?brain=${encodeURIComponent(brain)}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(await serverError(r))
        return r.json()
      })
      .then((d) => {
        setChats(
          (d.chats || []).map((c: { id: string; title: string; brain: string; updated: string }) => ({
            id: c.id,
            title: c.title || "Untitled",
            brain: c.brain || brain,
            at: c.updated ? new Date(c.updated).getTime() : 0,
          })),
        )
        setChatsError(null)
      })
      // A 401 used to read as "No saved chats yet" — the single most misleading
      // state in the port.
      .catch((e) => {
        setChats([])
        setChatsError((e as Error).message)
      })
  }
  useEffect(refresh, [brain])
  return { chats, refreshChats: refresh, chatsError }
}

export async function fetchChat(id: string): Promise<Turn[]> {
  const r = await apiFetch(`/api/chats/${encodeURIComponent(id)}`)
  if (!r.ok) throw new Error(await serverError(r))
  const d = await r.json()
  return (d.chat?.turns || []).map(
    (t: { role: string; text: string; sources?: Turn["sources"]; at?: number; error?: boolean }) => ({
      role: t.role === "user" ? "user" : "bot",
      text: t.text || "",
      sources: t.sources || undefined,
      // `at` is stored with every turn; dropping it here stamped every
      // restored message with the current clock time (legacy:1142).
      at: t.at,
      error: t.error,
    }),
  )
}

export async function saveChat(id: string, title: string, brain: string, turns: Turn[]) {
  const r = await apiFetch(`/api/chats?brain=${encodeURIComponent(brain)}`, {
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
  const r = await apiFetch("/api/brains/v2", { method: "POST", body: fd })
  const d = await r.json().catch(() => ({}))
  return { ok: r.status === 202, job_id: d.job_id, brain_id: d.brain_id, detail: d.detail, status: r.status }
}

export type JobStatus = {
  state: string
  error_code?: string | null
  files?: { client_file_id: string; stage: string; outcome?: string | null }[]
}

export async function getJob(jobId: string): Promise<JobStatus | null> {
  const r = await apiFetch(`/api/jobs/${encodeURIComponent(jobId)}`)
  if (!r.ok) return null
  const d = await r.json()
  return { state: d.job.state, error_code: d.job.error_code, files: d.files }
}

export function greeting(): string {
  const h = new Date().getHours()
  return h < 12 ? "Morning, how can I help?" : h < 17 ? "Afternoon, how can I help?" : "Evening, how can I help?"
}

export const DEFAULT_BRAIN = "company_brain"
