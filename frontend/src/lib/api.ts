import { useEffect, useState } from "react"

export type Brain = { name: string; chat_count?: number }
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
  useEffect(() => {
    fetch("/api/brains")
      .then((r) => r.json())
      .then((d) => setBrains((d.brains || []).map((b: { name: string }) => ({ name: b.name }))))
      .catch(() => {})
  }, [])
  return brains
}

export function useChats() {
  const [chats, setChats] = useState<ChatSummary[]>([])
  useEffect(() => {
    try {
      const out: ChatSummary[] = []
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i)
        if (!key || !key.startsWith("kestrel.chats.")) continue
        const brain = key.slice("kestrel.chats.".length)
        const all = JSON.parse(localStorage.getItem(key) || "[]") as {
          id: string
          title?: string
          at?: number
        }[]
        all.forEach((c) => out.push({ id: c.id, title: c.title || "Untitled", brain, at: c.at || 0 }))
      }
      out.sort((a, b) => b.at - a.at)
      setChats(out)
    } catch {
      /* storage unavailable */
    }
  }, [])
  return chats
}

export function greeting(): string {
  const h = new Date().getHours()
  return h < 12 ? "Morning, how can I help?" : h < 17 ? "Afternoon, how can I help?" : "Evening, how can I help?"
}

export const DEFAULT_BRAIN = "company_brain"
