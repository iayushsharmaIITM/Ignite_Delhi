import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import {
  BarChart3,
  Brain as BrainIcon,
  ExternalLink,
  FolderPlus,
  MessageSquare,
  Network,
  Plus,
  Trash2,
} from "lucide-react"
import { useAuthHeaders, useBrains, type Brain } from "@/lib/api"
import { t } from "@/lib/i18n"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { CreateBrainDialog } from "@/components/CreateBrainDialog"

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

type BrainStats = {
  ok: boolean
  nodes: number
  edges: number
  source?: string
}

type BrainWithStats = Brain & {
  is_demo?: boolean
  is_system?: boolean
  stats?: BrainStats
  statsLoading?: boolean
  statsError?: string
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

/* ------------------------------------------------------------------ */
/* Delete confirm (two-step inline)                                    */
/* ------------------------------------------------------------------ */

function DeleteButton({ name, onDeleted }: { name: string; onDeleted: () => void }) {
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const disarm = useCallback(() => {
    setArmed(false)
    if (timerRef.current) clearTimeout(timerRef.current)
  }, [])

  const handleClick = useCallback(async () => {
    if (!armed) {
      setArmed(true)
      timerRef.current = setTimeout(() => setArmed(false), 6000)
      return
    }
    disarm()
    setBusy(true)
    try {
      const headers = await useAuthHeaders()
      const r = await fetch(`/api/brains/${encodeURIComponent(name)}`, {
        method: "DELETE",
        headers,
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || !d.ok) throw new Error(d.detail || `HTTP ${r.status}`)
      toast.success(`Deleted "${name}"`)
      onDeleted()
    } catch (e) {
      toast.error((e as Error).message)
      setBusy(false)
    }
  }, [armed, name, onDeleted, disarm])

  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current) }, [])

  return (
    <Button
      variant="ghost"
      size="sm"
      className={cn(
        "text-muted-foreground",
        armed && "text-destructive hover:text-destructive",
      )}
      disabled={busy}
      onClick={handleClick}
    >
      <Trash2 className="h-3.5 w-3.5" />
      {busy ? "Deleting…" : armed ? "Confirm delete" : "Delete"}
    </Button>
  )
}

/* ------------------------------------------------------------------ */
/* Brain row                                                           */
/* ------------------------------------------------------------------ */

function BrainRow({ brain, onDeleted }: { brain: BrainWithStats; onDeleted: () => void }) {
  const qs = encodeURIComponent(brain.name)

  return (
    <li
      className={cn(
        "flex flex-col gap-3 rounded-xl border border-border bg-card p-4 transition-colors duration-150 ease-out hover:border-accent/40 sm:flex-row sm:items-center",
        brain.is_demo && "border-accent/30",
      )}
    >
      {/* Name + badges */}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-[14px] font-medium text-foreground">
            {brain.name}
          </span>
          {brain.is_demo && (
            <Badge variant="secondary" className="text-[10px] uppercase tracking-wider">
              demo
            </Badge>
          )}
          {brain.is_system && (
            <Badge variant="outline" className="text-[10px] uppercase tracking-wider">
              system
            </Badge>
          )}
        </div>

        {/* Stats */}
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[12px] text-muted-foreground">
          {brain.statsLoading ? (
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground/60" />
              measuring…
            </span>
          ) : brain.stats ? (
            <>
              <span className="inline-flex items-center gap-1">
                <Network className="h-3 w-3" />
                {brain.stats.nodes} nodes · {brain.stats.edges} edges
              </span>
              {brain.stats.source === "fixture" && (
                <span className="text-[11px] italic">offline snapshot</span>
              )}
            </>
          ) : brain.statsError ? (
            <span className="text-[12px] text-destructive">{brain.statsError}</span>
          ) : null}

          {brain.chat_count !== undefined && (
            <span className="inline-flex items-center gap-1">
              <MessageSquare className="h-3 w-3" />
              {brain.chat_count} chat{brain.chat_count === 1 ? "" : "s"}
            </span>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex flex-none flex-wrap items-center gap-1.5">
        <Button asChild variant="secondary" size="sm">
          <a href={`/?brain=${qs}`}>
            <ExternalLink className="h-3.5 w-3.5" />
            Open
          </a>
        </Button>
        <Button asChild variant="ghost" size="sm">
          <a href={`/graph?brain=${qs}`}>
            <BarChart3 className="h-3.5 w-3.5" />
            Graph
          </a>
        </Button>
        <Button asChild variant="ghost" size="sm">
          <a href={`/upload?brain=${qs}`}>
            <FolderPlus className="h-3.5 w-3.5" />
            Add documents
          </a>
        </Button>
        {!brain.is_demo && !brain.is_system && (
          <DeleteButton name={brain.name} onDeleted={onDeleted} />
        )}
      </div>
    </li>
  )
}

/* ------------------------------------------------------------------ */
/* Empty state                                                         */
/* ------------------------------------------------------------------ */

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-col items-center gap-4 rounded-xl border border-dashed border-border bg-card px-6 py-16 text-center">
      <div className="grid h-14 w-14 place-items-center rounded-2xl bg-accent-dim">
        <BrainIcon className="h-7 w-7 text-accent" />
      </div>
      <div>
        <p className="text-[15px] font-semibold text-foreground">No brains yet</p>
        <p className="mt-1 text-[13px] text-muted-foreground">
          Create your first brain from documents — it takes about a minute to build.
        </p>
      </div>
      <Button onClick={onCreate} className="rounded-lg font-semibold">
        <Plus className="h-4 w-4" />
        New brain
      </Button>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* BrainsPage                                                          */
/* ------------------------------------------------------------------ */

export function BrainsPage() {
  const { brains, refreshBrains } = useBrains()
  const [createOpen, setCreateOpen] = useState(false)
  const [enriched, setEnriched] = useState<BrainWithStats[]>([])

  /* Merge API brains with demo/system flags and lazy-load stats */
  useEffect(() => {
    const mapped: BrainWithStats[] = brains.map((b) => ({
      ...b,
      is_demo: b.name === "demo" || b.name === "company_brain",
      is_system: b.name.startsWith("_") || b.name === "default",
      statsLoading: true,
    }))
    setEnriched(mapped)

    /* Fetch stats for each brain in parallel */
    mapped.forEach((b) => {
      fetch(`/api/stats?dataset=${encodeURIComponent(b.name)}`)
        .then((r) => r.json())
        .then((d: BrainStats) => {
          setEnriched((prev) =>
            prev.map((x) =>
              x.name === b.name
                ? { ...x, stats: d, statsLoading: false }
                : x,
            ),
          )
        })
        .catch(() => {
          setEnriched((prev) =>
            prev.map((x) =>
              x.name === b.name
                ? { ...x, statsLoading: false, statsError: "could not read graph size" }
                : x,
            ),
          )
        })
    })
  }, [brains])

  const handleDeleted = useCallback(() => {
    refreshBrains()
  }, [refreshBrains])

  return (
    <div className="flex-1 overflow-y-auto" aria-label="Brains">
      <div className="mx-auto max-w-[780px] px-6 py-10">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-[22px] font-semibold tracking-tight text-foreground">
              {t("nav.brains")}
            </h1>
            <p className="mt-1 text-[13.5px] text-muted-foreground">
              Every brain in this workspace. The demo brain is pre-built;
              the rest were created from documents someone uploaded.
            </p>
          </div>
          <Button
            onClick={() => setCreateOpen(true)}
            className="flex-none rounded-lg font-semibold"
          >
            <Plus className="h-4 w-4" />
            {t("nav.new_brain")}
          </Button>
        </div>

        {/* List */}
        {enriched.length === 0 ? (
          <div className="mt-8">
            <EmptyState onCreate={() => setCreateOpen(true)} />
          </div>
        ) : (
          <ul className="mt-6 flex flex-col gap-3" aria-label="Brain list">
            {enriched.map((b) => (
              <BrainRow key={b.name} brain={b} onDeleted={handleDeleted} />
            ))}
          </ul>
        )}

        {/* Footer */}
        <footer className="mt-10 flex flex-wrap gap-4 border-t border-border pt-5 text-[12px] text-muted-foreground">
          <a href="/" className="text-accent hover:underline">
            demo dashboard
          </a>
          <a href="/upload" className="text-accent hover:underline">
            new brain
          </a>
          <a href="/health" className="text-accent hover:underline">
            /health
          </a>
        </footer>
      </div>

      <CreateBrainDialog
        open={createOpen}
        onClose={(created) => {
          setCreateOpen(false)
          refreshBrains()
          if (created) {
            toast.success(`Brain "${created}" created`)
          }
        }}
      />
    </div>
  )
}
