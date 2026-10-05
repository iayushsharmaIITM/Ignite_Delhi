import { useEffect, useState } from "react"
import { awaitClerkBoot, getClerkToken } from "@/lib/clerk"

export type Brain = { name: string; chat_count?: number; is_demo?: boolean; is_system?: boolean }
export type ChatSummary = { id: string; title: string; brain: string; at: number; created?: number }
export type WorkStep = { label: string; at: number; ms?: number }
export type Attachment = { name: string; kind: "image" | "file"; size: number; url?: string }

export type Turn = {
  role: "user" | "bot"
  text: string
  sources?: { source: string; excerpt?: string }[]
  at?: number
  /** Legacy .bubble.err: the turn is a failure state, not model output. */
  error?: boolean
  attachments?: Attachment[]
  steps?: WorkStep[]
  workedMs?: number
  stopped?: boolean
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

export type ApiConfig = {
  authMode?: string
  publishableKey?: string
  maxTurns?: number
  brainCreateV2?: boolean
}

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

/**
 * How many turns one chat may hold, as the SERVER says (CH-1).
 *
 * The client used to hardcode a 60-turn window that no server rule matched, so
 * it trimmed history on its own initiative. The cap now comes from the same
 * endpoint that enforces it; 500 is only the fallback for a config that cannot
 * be read.
 */
export function turnCap(): Promise<number> {
  return apiConfig().then((c) => Number(c.maxTurns) || 500)
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

export function useBrains(enabled = true) {
  const [brains, setBrains] = useState<Brain[]>([])
  const [brainsError, setBrainsError] = useState<string | null>(null)
  const refresh = () => {
    // CH-12: in clerk mode a signed-out visitor has no right to ask, and
    // prefetching anyway produced two console errors on every load — the API
    // was correct to 401, the client was wrong to call.
    if (!enabled) { setBrains([]); setBrainsError(null); return }
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
  useEffect(refresh, [enabled])
  return { brains, refreshBrains: refresh, brainsError }
}

/**
 * Server-backed chat history — EVERY brain, not just the open one.
 *
 * Legacy reads all `kestrel.chats.*` keys and merges the server rows, so the
 * sidebar keeps working on /brains, /graph and /upload and "Grouped by brain"
 * can actually show more than one folder (shell.js:55-68,128-214). The port
 * asked for one brain and only while the chat view was open, so every other
 * view claimed "No saved chats yet".
 */
export function useChats(enabled = true) {
  const [chats, setChats] = useState<ChatSummary[]>([])
  const [chatsError, setChatsError] = useState<string | null>(null)
  // CH-7: the server now reports the UN-CAPPED count. Without it a page that
  // stopped at the limit looked exactly like a complete history.
  const [total, setTotal] = useState(0)
  const refresh = () => {
    // CH-12: no session, no call — see useBrains.
    if (!enabled) { setChats([]); setChatsError(null); setTotal(0); return }
    // The sidebar caps what it RENDERS; it must not also cap what it KNOWS, or
    // a folder with 23 chats shows 5 with no sign the rest exist (and a delete
    // looks like a no-op because the next one slides in).
    apiFetch(`/api/chats?limit=500`)
      .then(async (r) => {
        if (!r.ok) throw new Error(await serverError(r))
        return r.json()
      })
      .then((d) => {
        setChats(
          (d.chats || []).map(
            (c: { id: string; title: string; brain: string; updated: string; created?: string }) => ({
              id: c.id,
              title: c.title || "Untitled",
              brain: c.brain,
              at: c.updated ? new Date(c.updated).getTime() : 0,
              // Sorting by "Created" was a no-op without this: every row fell
              // back to `updated` (storage.list_chats has returned `created`
              // all along).
              created: c.created ? new Date(c.created).getTime() : undefined,
            }),
          ),
        )
        setTotal(Number(d.total ?? (d.chats || []).length))
        setChatsError(null)
      })
      // A 401 used to read as "No saved chats yet" — the single most misleading
      // state in the port.
      .catch((e) => {
        setChats([])
        setChatsError((e as Error).message)
      })
  }
  useEffect(refresh, [enabled])
  return { chats, refreshChats: refresh, chatsError, total,
           truncated: total > chats.length }
}

export async function fetchChat(id: string): Promise<Turn[]> {
  const r = await apiFetch(`/api/chats/${encodeURIComponent(id)}`)
  if (!r.ok) throw new Error(await serverError(r))
  const d = await r.json()
  return (d.chat?.turns || []).map((t: Partial<Turn> & { role: string }) => ({
    role: t.role === "user" ? "user" : "bot",
    text: t.text || "",
    sources: t.sources || undefined,
    // These four were dropped on restore: every message got the current clock
    // time, attachments vanished, and each answer lost its working log.
    at: t.at,
    error: t.error,
    attachments: t.attachments,
    steps: t.steps,
    workedMs: t.workedMs,
    stopped: t.stopped,
  }))
}

export async function saveChat(
  id: string, title: string, brain: string, turns: Turn[], trim = false,
): Promise<{ ok: boolean; status: number }> {
  const r = await apiFetch(`/api/chats?brain=${encodeURIComponent(brain)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // `trim` tells the server this save is SHORTER than what it holds on
    // purpose. Without it a shorter window is refused (CH-1), because the
    // rewrite deletes before it re-inserts.
    body: JSON.stringify({ id, title: title.slice(0, 120), turns, trim }),
  })
  // The status, not just a boolean: the caller must tell "deleted elsewhere"
  // (410) from "another tab got there first" (409) from a plain failure.
  return { ok: r.ok, status: r.status }
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

/**
 * The default create path: `POST /api/brains`, synchronous, nothing to poll.
 *
 * This is what the dialog used to be pointed at before the v2 job path existed.
 * `/api/brains/v2` is flag-gated (`KESTREL_JOBS_V2=1`) and answers 404 without it,
 * so a client that assumed v2 was there shipped a "Create a brain" button that
 * could only ever fail — on every deployment that had not turned the flag on,
 * which is all of them. Use `createBrain`, which asks the server which path
 * exists; this one is exported for the callers that already know.
 */
export async function createBrainLegacy(
  name: string,
  files: File[],
): Promise<{ ok: boolean; partial: boolean; name?: string; detail: string; status: number }> {
  const fd = new FormData()
  fd.append("name", name)
  files.forEach((f) => fd.append("files", f))
  const r = await apiFetch("/api/brains", { method: "POST", body: fd })
  const d = await r.json().catch(() => ({}))
  return {
    ok: r.ok && d.ok !== false,
    partial: !!d.partial,
    name: d.name,
    detail: d.detail || d.error || "",
    status: r.status,
  }
}

/** Which create path this server actually answers. */
export function brainCreateV2Enabled(): Promise<boolean> {
  return apiConfig().then((c) => c.brainCreateV2 === true)
}

export type JobStatus = {
  state: string
  error_code?: string | null
  files?: { client_file_id: string; stage: string; outcome?: string | null }[]
}

export async function getJob(jobId: string, signal?: AbortSignal): Promise<JobStatus | null> {
  const r = await apiFetch(`/api/jobs/${encodeURIComponent(jobId)}`, { signal })
  if (!r.ok) return null
  const d = await r.json().catch(() => ({}))
  return { state: d.job?.state, error_code: d.job?.error_code, files: d.files }
}

// greeting() lived here as hardcoded English. The shell now resolves the
// time-of-day greeting through the dictionary (i18n keys greet.morning /
// greet.afternoon / greet.evening, the same keys static/index.html:804 uses),
// so a language switch actually changes it.

export const DEFAULT_BRAIN = "company_brain"
