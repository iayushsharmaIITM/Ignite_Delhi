import { useEffect, useMemo, useState } from "react"
import { apiFetch, serverError } from "@/lib/api"

type GNode = { id: string; label?: string; degree?: number }
type GEdge = { source_node_id?: string; target_node_id?: string; source?: string; target?: string }

type Props = { brain: string }

/**
 * Minimal React graph view (Phase 9): fetches /api/graph for the active brain
 * and renders a deterministic circle layout. For full interactive exploration
 * the legacy graph page remains linked — labeled, not silent.
 */
export function GraphView({ brain }: Props) {
  const [nodes, setNodes] = useState<GNode[]>([])
  const [edges, setEdges] = useState<GEdge[]>([])
  const [source, setSource] = useState<string>("")
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<GNode | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    setError(null)
    setSelected(null)
    apiFetch(`/api/graph?brain=${encodeURIComponent(brain)}`)
      .then(async (r) => {
        // 401/403/5xx answers with JSON, so without this the view rendered the
        // "graph is empty — run ingest.py" state for a permission error.
        if (!r.ok) throw new Error(await serverError(r))
        return r.json()
      })
      .then((d) => {
        setNodes(d.nodes || [])
        setEdges(d.edges || [])
        setSource(d.source || "")
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }, [brain])

  const CAP = 120
  const shown = useMemo(() => nodes.slice(0, CAP), [nodes])
  const pos = useMemo(() => {
    const R = 260, CX = 420, CY = 300
    const map = new Map<string, { x: number; y: number }>()
    shown.forEach((n, i) => {
      const a = (i / Math.max(shown.length, 1)) * Math.PI * 2 - Math.PI / 2
      map.set(n.id, { x: CX + R * Math.cos(a), y: CY + R * Math.sin(a) })
    })
    return map
  }, [shown])

  const labelOf = (n: GNode) =>
    (n.label || "").slice(0, 26) || n.id.slice(0, 12)
  const edgeEnds = (e: GEdge): [string, string] | null => {
    const s = e.source_node_id || e.source
    const t = e.target_node_id || e.target
    return s && t && pos.has(s) && pos.has(t) ? [s, t] : null
  }

  return (
    <div className="flex-1 overflow-y-auto" aria-label="Knowledge graph">
      <div className="mx-auto max-w-[900px] px-6 py-10">
        <h1 className="text-[22px] font-semibold tracking-tight text-foreground">
          Knowledge graph
        </h1>
        <p className="mt-1 text-[13.5px] text-muted-foreground">
          {loading ? "Loading the graph…" :
           error ? `Could not load the graph: ${error}` :
           `${nodes.length} nodes · ${edges.length} edges in “${brain}”` +
           (source ? ` (${source})` : "")}
        </p>

        {!loading && !error && nodes.length === 0 && (
          <p className="mt-6 rounded-xl border border-border bg-card p-5 text-sm text-muted-foreground">
            This brain's graph is empty. Create a brain and add documents — the
            graph builds as files are ingested.
          </p>
        )}

        {!loading && nodes.length > CAP && (
          <p className="mt-3 rounded-lg border border-line bg-panel-2 px-3 py-2 text-xs text-muted-foreground">
            Showing the first {CAP} of {nodes.length} nodes for readability — the
            full interactive graph remains in the legacy view (linked below).
          </p>
        )}

        {nodes.length > 0 && (
          <div className="mt-6 flex flex-wrap items-center gap-4 text-[11px] text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full border border-accent bg-accent-dim" aria-hidden /> entity
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block h-px w-5 bg-accent/40" aria-hidden /> relation
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full border border-accent bg-accent" aria-hidden /> selected
            </span>
            <span aria-hidden>· click a node to inspect</span>
          </div>
        )}
        {nodes.length > 0 && (
          <div className="mt-6 overflow-hidden rounded-[14px] border border-border bg-card">
            <svg viewBox="0 0 840 600" className="h-auto w-full" role="img"
                 aria-label={`Knowledge graph of ${brain}: ${nodes.length} nodes, ${edges.length} edges`}>
              {edges.map((e, i) => {
                const ends = edgeEnds(e)
                if (!ends) return null
                const [a, b] = [pos.get(ends[0])!, pos.get(ends[1])!]
                return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                             stroke="var(--accent)" strokeOpacity="0.25" strokeWidth="1" />
              })}
              {shown.map((n) => {
                const p = pos.get(n.id)!
                const isSel = selected?.id === n.id
                return (
                  <g key={n.id} onClick={() => setSelected(isSel ? null : n)}
                     className="cursor-pointer" role="button"
                     aria-label={labelOf(n)}>
                    <circle cx={p.x} cy={p.y} r={isSel ? 10 : 6}
                            fill={isSel ? "var(--accent)" : "var(--accent-dim)"}
                            stroke="var(--accent)" strokeWidth="1.5"
                            className="node-dot cursor-pointer transition-all duration-150 ease-out" />
                    <text x={p.x + 10} y={p.y + 4} fontSize="11"
                          fill={isSel ? "var(--ink)" : "var(--muted)"}>
                      {labelOf(n)}
                    </text>
                  </g>
                )
              })}
            </svg>
          </div>
        )}

        {selected && (
          <div className="mt-4 rounded-[14px] border border-border bg-card p-4">
            <div className="text-sm font-semibold text-foreground">{labelOf(selected)}</div>
            <div className="mt-1 text-xs text-muted-foreground">
              id {selected.id.slice(0, 18)}…
              {selected.degree !== undefined ? ` · ${selected.degree} connections` : ""}
            </div>
          </div>
        )}

        {nodes.length > 0 && (
          <p className="mt-4 text-[11.5px] text-muted-foreground">
            This is the simplified in-app view. The full interactive graph
            (expand, filter, search) is available in the{" "}
            <a href={`/graph?brain=${encodeURIComponent(brain)}`}
               className="text-accent underline">legacy graph page</a>.
          </p>
        )}
      </div>
    </div>
  )
}
