import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { apiFetch, serverError } from "@/lib/api"

type RawNode = {
  id: string
  label?: string
  type?: string
  properties?: Record<string, unknown> | null
  degree?: number
}
type RawEdge = {
  source?: string; target?: string
  source_node_id?: string; target_node_id?: string
  from?: string; to?: string; start?: string; end?: string
  label?: string; type?: string; rel?: string
}
type Laid = {
  id: string; type: string; label: string
  properties: Record<string, unknown> | null
  r: number; x: number; y: number; vx: number; vy: number
}
type Link = { source: string; target: string; label: string | null }
type Props = { brain: string }

/**
 * The knowledge graph, ported from the legacy static/graph.html renderer.
 *
 * The behaviour being preserved is progressive disclosure: the graph opens as
 * the twelve most-connected nodes, and clicking one reveals its sub-nodes. A
 * wall of every node is readable for about a second, which is why the previous
 * in-app view (a static circle capped at 120 nodes, with an inspector that
 * showed only an id) was never a replacement for it.
 *
 * Layout and camera live in refs, not state: the simulation repaints sixty
 * times a second while it settles, and driving that through React would
 * re-render the whole panel per frame. State holds only what the DOM shows.
 */

const ROOTS = 12
const SPRING_LEN = 135
const SPRING_K = 0.012
const REPULSION = 1500
const REPULSE_MAX_D2 = 160000   // 400px: beyond it, two nodes ignore each other
const CENTER_PULL = 0.0009
const DAMPING = 0.86
const ALPHA_MIN = 0.02
const ALPHA_DECAY = 0.99
const CAM_EASE = 0.16

// Cognee prefixes some node ids with their type and a long hex; the suffix is
// noise to a human reading the graph. Same rule as the legacy page.
const ID_SUFFIX = /^([A-Za-z]+)_[0-9a-f-]{8,}$/

function endsOf(e: RawEdge): [string | undefined, string | undefined] {
  return [
    e.source ?? e.source_node_id ?? e.from ?? e.start,
    e.target ?? e.target_node_id ?? e.to ?? e.end,
  ]
}
function verbOf(e: RawEdge): string | null {
  return e.label ?? e.type ?? e.rel ?? null
}

type Palette = {
  accent: string; fg: string; muted: string; muted2: string
  line: string; panel2: string; bg: string; card: string
}

function readTokens(): Palette {
  const cs = getComputedStyle(document.documentElement)
  const v = (n: string, fallback: string) => (cs.getPropertyValue(n) || "").trim() || fallback
  return {
    accent: v("--accent", "#b45309"),
    fg: v("--fg", "#201d18"),
    muted: v("--muted", "#5f5a52"),
    muted2: v("--muted-2", "#6f6a60"),
    line: v("--line-2", "rgba(128,128,128,.25)"),
    panel2: v("--panel-2", "#f3f1ec"),
    bg: v("--bg", "#f7f5f2"),
    card: v("--panel", "#ffffff"),
  }
}

// Node types are coloured so the picture reads as structure rather than
// spaghetti. The legacy page hardcoded ten hexes; these are derived from the
// theme's own tokens, so the graph follows light/dark instead of fighting it.
function typePalette(p: Palette): string[] {
  const parse = (c: string): [number, number, number, number] => {
    const m = c.match(/#([0-9a-f]{3}|[0-9a-f]{6})/i)
    if (m) {
      const h = m[1].length === 3 ? m[1].split("").map(x => x + x).join("") : m[1]
      return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), 1]
    }
    const rms = c.match(/rgba?\(([^)]+)\)/i)
    if (rms) {
      const n = rms[1].split(/[\s,\/]+/).map(x => parseFloat(x))
      return [n[0] || 0, n[1] || 0, n[2] || 0, n.length > 3 ? n[3] : 1]
    }
    return [128, 128, 128, 1]
  }
  const mix = (a: string, b: string, t: number) => {
    const x = parse(a), y = parse(b)
    const c = (i: number) => Math.round(x[i] + (y[i] - x[i]) * t)
    return `rgb(${c(0)}, ${c(1)}, ${c(2)})`
  }
  const out = [p.accent]
  for (let i = 1; i < 10; i++) out.push(mix(p.fg, p.muted2, i / 9))
  return out
}

export function GraphView({ brain }: Props) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [counts, setCounts] = useState({ nodes: 0, edges: 0 })
  const [source, setSource] = useState("")
  const [selected, setSelected] = useState<Laid | null>(null)
  const [legend, setLegend] = useState<{ type: string; n: number }[]>([])
  const [core, setCore] = useState<Laid[]>([])
  const [expandedCount, setExpandedCount] = useState(0)
  // The zoom level is camera state, and the camera lives in a ref because the
  // simulation repaints sixty times a second. Surfaces need it anyway (a reader
  // wants to know whether they are looking at the whole graph or one cluster),
  // so it is published on the two events that change it rather than every frame.
  const [zoomPct, setZoomPct] = useState(100)

  const wrapRef = useRef<HTMLDivElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  const nodesRef = useRef<Laid[]>([])
  const edgesRef = useRef<Link[]>([])
  const byIdRef = useRef<Map<string, Laid>>(new Map())
  const adjRef = useRef<Map<string, Set<string>>>(new Map())
  const rootsRef = useRef<string[]>([])
  const expandedRef = useRef<Set<string>>(new Set())
  const selectedRef = useRef<string | null>(null)
  const camRef = useRef({ x: 0, y: 0, k: 1 })
  const camTargetRef = useRef<{ x: number; y: number; k: number } | null>(null)
  const alphaRef = useRef(0)
  const runningRef = useRef(false)
  const sizeRef = useRef({ w: 0, h: 0, dpr: 1 })
  const palRef = useRef<{ colors: string[]; p: Palette }>({ colors: [], p: readTokens() })
  const typeColorRef = useRef<Record<string, string>>({})
  const typeOrderRef = useRef<string[]>([])
  const dragRef = useRef<{ x: number; y: number } | null>(null)
  const movedRef = useRef(0)

  const neighbours = (id: string): Set<string> => adjRef.current.get(id) ?? new Set([id])

  const visibleIds = useCallback(() => {
    const out = new Set(rootsRef.current)
    for (const id of expandedRef.current) {
      out.add(id)
      for (const nb of neighbours(id)) out.add(nb)
    }
    return out
  }, [])

  // Fit the camera on a set of nodes: clamped so one node cannot fill the
  // screen and a wide set never shrinks to a dot.
  const fitTo = useCallback((ids: Iterable<string>, pad = 110, maxK = 1.5) => {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity, any = false
    for (const id of ids) {
      const nd = byIdRef.current.get(id)
      if (!nd) continue
      any = true
      minX = Math.min(minX, nd.x); maxX = Math.max(maxX, nd.x)
      minY = Math.min(minY, nd.y); maxY = Math.max(maxY, nd.y)
    }
    if (!any) return
    const { w, h } = sizeRef.current
    const bw = Math.max(maxX - minX, 1), bh = Math.max(maxY - minY, 1)
    const k = Math.min(maxK, Math.max(0.3, Math.min((w - pad * 2) / bw, (h - pad * 2) / bh)))
    camTargetRef.current = { k, x: w / 2 - ((minX + maxX) / 2) * k, y: h / 2 - ((minY + maxY) / 2) * k }
    wake()
  }, [])

  const draw = useCallback(() => {
    const cv = canvasRef.current
    if (!cv) return
    const ctx = cv.getContext("2d")
    if (!ctx) return
    const { w: W, h: H, dpr } = sizeRef.current
    if (!W || !H) return
    const nodes = nodesRef.current, edges = edgesRef.current, byId = byIdRef.current
    const cam = camRef.current
    const p = palRef.current.p
    // Colours come from a table built with the model, in the same order the
    // legend renders. Assigning them lazily in first-painted order meant the
    // swatch beside a type's name could describe a different type's nodes.
    const colorFor = (t: string) => typeColorRef.current[t] ?? palRef.current.colors[0]

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, W, H)
    ctx.fillStyle = p.card
    ctx.fillRect(0, 0, W, H)

    const vis = visibleIds()
    const selId = selectedRef.current
    const focus = selId ? neighbours(selId) : null
    const focusing = !!(focus && focus.size > 1)
    const wanted = (id: string) => !focus || focus.has(id)

    // Focusing on a node drops the rest of the graph entirely rather than
    // dimming it: background nodes keep competing for attention, and a radial
    // lift keeps the empty field from reading as a flat rectangle.
    if (focusing && selId) {
      const sel = byId.get(selId)
      if (sel) {
        const cx = cam.x + sel.x * cam.k, cy = cam.y + sel.y * cam.k
        const radius = Math.max(W, H) * 0.66
        const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius)
        g.addColorStop(0, p.panel2)
        g.addColorStop(0.5, p.bg)
        g.addColorStop(1, p.card)
        ctx.fillStyle = g
        ctx.fillRect(0, 0, W, H)
      }
    }

    ctx.save()
    ctx.translate(cam.x, cam.y)
    ctx.scale(cam.k, cam.k)

    ctx.globalAlpha = 1
    ctx.strokeStyle = p.line
    ctx.lineWidth = 1.7 / cam.k
    for (const e of edges) {
      if (!vis.has(e.source) || !vis.has(e.target)) continue
      if (!(wanted(e.source) || wanted(e.target))) continue
      const a = byId.get(e.source), b = byId.get(e.target)
      if (!a || !b) continue
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke()
    }

    for (const nd of nodes) {
      if (!vis.has(nd.id) || !wanted(nd.id)) continue
      const isSel = nd.id === selId
      ctx.beginPath()
      ctx.arc(nd.x, nd.y, isSel ? nd.r * 1.7 : nd.r, 0, Math.PI * 2)
      ctx.fillStyle = colorFor(nd.type)
      ctx.fill()
      if (isSel) {
        ctx.strokeStyle = p.accent
        ctx.lineWidth = 2 / cam.k
        ctx.stroke()
      }
    }

    ctx.font = "11px -apple-system, system-ui, sans-serif"
    ctx.textAlign = "center"
    for (const nd of nodes) {
      if (!vis.has(nd.id) || !wanted(nd.id)) continue
      const isSel = nd.id === selId
      if (!isSel && cam.k <= 0.85) continue
      if (nd.label.length > 34) continue
      ctx.fillStyle = isSel ? p.accent : p.muted
      ctx.fillText(nd.label, nd.x, nd.y - nd.r - 5)
    }
    ctx.restore()
  }, [visibleIds])

  const frame = useCallback(() => {
    const settling = alphaRef.current > ALPHA_MIN
    if (settling) {
      const a = alphaRef.current
      const nodes = nodesRef.current, edges = edgesRef.current, byId = byIdRef.current
      const { w: W, h: H } = sizeRef.current
      const cx = W / 2, cy = H / 2
      for (const n of nodes) {
        n.vx *= DAMPING; n.vy *= DAMPING
        n.vx += (cx - n.x) * CENTER_PULL * a
        n.vy += (cy - n.y) * CENTER_PULL * a
      }
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const A = nodes[i], B = nodes[j]
          let dx = B.x - A.x, dy = B.y - A.y
          const d2 = dx * dx + dy * dy || 1
          if (d2 > REPULSE_MAX_D2) continue
          const f = REPULSION / d2
          const d = Math.sqrt(d2)
          dx /= d; dy /= d
          A.vx -= dx * f * a; A.vy -= dy * f * a
          B.vx += dx * f * a; B.vy += dy * f * a
        }
      }
      for (const e of edges) {
        const A = byId.get(e.source), B = byId.get(e.target)
        if (!A || !B) continue
        const dx = B.x - A.x, dy = B.y - A.y
        const d = Math.sqrt(dx * dx + dy * dy) || 1
        const f = (d - SPRING_LEN) * SPRING_K * a
        A.vx += (dx / d) * f; A.vy += (dy / d) * f
        B.vx -= (dx / d) * f; B.vy -= (dy / d) * f
      }
      for (const n of nodes) { n.x += n.vx; n.y += n.vy }
      alphaRef.current *= ALPHA_DECAY
    }
    const t = camTargetRef.current
    let easing = false
    if (t) {
      const cam = camRef.current
      cam.x += (t.x - cam.x) * CAM_EASE
      cam.y += (t.y - cam.y) * CAM_EASE
      cam.k += (t.k - cam.k) * CAM_EASE
      if (Math.abs(t.x - cam.x) < 0.6 && Math.abs(t.y - cam.y) < 0.6 && Math.abs(t.k - cam.k) < 0.002) {
        camRef.current = { x: t.x, y: t.y, k: t.k }
        camTargetRef.current = null
        setZoomPct(Math.round(t.k * 100))
      } else easing = true
    }
    draw()
    if (settling || easing) requestAnimationFrame(frame)
    else runningRef.current = false
  }, [draw])

  const wake = useCallback(() => {
    if (!runningRef.current) { runningRef.current = true; requestAnimationFrame(frame) }
  }, [frame])

  const pick = useCallback((clientX: number, clientY: number) => {
    const cv = canvasRef.current
    if (!cv) return
    const rect = cv.getBoundingClientRect()
    const cam = camRef.current
    const wx = (clientX - rect.left - cam.x) / cam.k
    const wy = (clientY - rect.top - cam.y) / cam.k
    const vis = visibleIds()
    let hit: Laid | null = null
    for (const nd of nodesRef.current) {
      if (!vis.has(nd.id)) continue
      const d = Math.hypot(nd.x - wx, nd.y - wy)
      if (d <= Math.max(nd.r * 1.7, 10) + 4) { hit = nd; break }
    }
    if (!hit) {
      selectedRef.current = null
      setSelected(null)
      wake()
      return
    }
    // Clicking a node opens its sub-nodes; clicking it again closes them. That
    // two-way behaviour is what makes 200+ nodes explorable instead of loud.
    const open = expandedRef.current.has(hit.id)
    if (open) expandedRef.current.delete(hit.id)
    else expandedRef.current.add(hit.id)
    setExpandedCount(expandedRef.current.size)
    selectedRef.current = open ? null : hit.id
    setSelected(open ? null : hit)
    if (!open) fitTo(neighbours(hit.id), 90, 1.25)
    else fitTo(rootsRef.current, 110, 1.0)
    wake()
  }, [visibleIds, fitTo, wake])

  useEffect(() => {
    const wrap = wrapRef.current, cv = canvasRef.current
    if (!wrap || !cv) return
    const ro = new ResizeObserver(() => {
      const dpr = window.devicePixelRatio || 1
      const w = wrap.clientWidth, h = wrap.clientHeight
      if (!w || !h) return
      sizeRef.current = { w, h, dpr }
      cv.width = w * dpr; cv.height = h * dpr
      cv.style.width = w + "px"; cv.style.height = h + "px"
      draw()
    })
    ro.observe(wrap)
    return () => ro.disconnect()
  }, [draw])

  // The graph must follow a theme change without a reload: canvas colours are
  // resolved once, so a light-mode palette left running in dark mode is a real
  // defect rather than a cosmetic one.
  useEffect(() => {
    const apply = () => {
      const p = readTokens()
      const colors = typePalette(p)
      palRef.current = { p, colors }
      // Same assignment as the model build, so a repaint never re-shuffles types.
      const next: Record<string, string> = {}
      typeOrderRef.current.forEach((t, i) => { next[t] = colors[i % Math.max(colors.length, 1)] })
      typeColorRef.current = next
      draw()
    }
    apply()
    const mo = new MutationObserver(apply)
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] })
    return () => mo.disconnect()
  }, [draw])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setSelected(null)
    selectedRef.current = null
    setCore([])
    expandedRef.current = new Set()
    setExpandedCount(0)
    apiFetch(`/api/graph?dataset=${encodeURIComponent(brain)}`)
      .then(async r => {
        // A non-200 answers with JSON; without this a 403 rendered the same
        // "graph is empty" state as a genuinely new brain.
        if (!r.ok) throw new Error(await serverError(r))
        return r.json()
      })
      .then(d => {
        if (cancelled) return
        // /api/graph answers 200 with {error, nodes: [], edges: []} when the
        // tenant is unreachable and no snapshot covers this brain. Showing
        // "the graph is empty" there would be a lie about an outage.
        if (d.error) throw new Error(String(d.error))
        const rawNodes: RawNode[] = d.nodes || []
        const rawEdges: RawEdge[] = d.edges || []
        const { w, h } = sizeRef.current
        const W = w || 840, H = h || 520
        const list: Laid[] = rawNodes.map((n, i) => {
          const label = (n.label || n.id || "").replace(ID_SUFFIX, "$1")
          return {
            id: n.id,
            type: n.type || "Node",
            label,
            properties: n.properties && typeof n.properties === "object" ? n.properties : null,
            r: 4 + Math.min(7, label.length / 8),
            x: W / 2 + Math.cos(i * 2.399) * (60 + Math.random() * 220),
            y: H / 2 + Math.sin(i * 2.399) * (60 + Math.random() * 220),
            vx: 0, vy: 0,
          }
        })
        const byId = new Map(list.map(n => [n.id, n]))
        const links: Link[] = []
        for (const e of rawEdges) {
          const [s, t] = endsOf(e)
          if (s && t && byId.has(s) && byId.has(t)) links.push({ source: s, target: t, label: verbOf(e) })
        }
        const adj = new Map<string, Set<string>>()
        for (const n of list) adj.set(n.id, new Set([n.id]))
        for (const e of links) {
          adj.get(e.source)!.add(e.target)
          adj.get(e.target)!.add(e.source)
        }
        nodesRef.current = list
        edgesRef.current = links
        byIdRef.current = byId
        adjRef.current = adj
        rootsRef.current = [...list]
          .map(n => ({ id: n.id, deg: (adj.get(n.id)?.size ?? 1) - 1 }))
          .sort((a, b) => b.deg - a.deg)
          .slice(0, ROOTS)
          .map(x => x.id)
        setCounts({ nodes: list.length, edges: links.length })
        setSource(d.source || "")
        const tally: Record<string, number> = {}
        for (const n of list) tally[n.type] = (tally[n.type] || 0) + 1
        const ordered = Object.entries(tally).map(([type, n]) => ({ type, n }))
          .sort((a, b) => b.n - a.n)
        // Types are coloured in this same order, and the legend renders the same
        // order, so a swatch always describes the type printed beside it. A type
        // beyond the palette wraps rather than going uncoloured.
        typeOrderRef.current = ordered.map(o => o.type)
        const colors = palRef.current.colors
        const next: Record<string, string> = {}
        typeOrderRef.current.forEach((t, i) => { next[t] = colors[i % Math.max(colors.length, 1)] })
        typeColorRef.current = next
        setLegend(ordered.slice(0, 10))
        setCore(rootsRef.current.map(id => byId.get(id)!).filter(Boolean))
        alphaRef.current = 1
        camRef.current = { x: 0, y: 0, k: 1 }
        fitTo(rootsRef.current, 110, 1.0)
        wake()
      })
      .catch(e => { if (!cancelled) setError(String(e?.message || e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [brain, fitTo, wake])

  const zoomAt = (px: number, py: number, factor: number) => {
    const cam = camRef.current
    const k = Math.min(4, Math.max(0.25, cam.k * factor))
    camRef.current = { k, x: px - (px - cam.x) * (k / cam.k), y: py - (py - cam.y) * (k / cam.k) }
    camTargetRef.current = null
    setZoomPct(Math.round(k * 100))
    wake()
  }

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault()
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    zoomAt(e.clientX - rect.left, e.clientY - rect.top, e.deltaY < 0 ? 1.12 : 0.89)
  }
  const onPointerDown = (e: React.PointerEvent) => {
    const cam = camRef.current
    dragRef.current = { x: e.clientX - cam.x, y: e.clientY - cam.y }
    movedRef.current = 0
  }
  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragRef.current) return
    movedRef.current += Math.abs(e.movementX || 0) + Math.abs(e.movementY || 0)
    const cam = camRef.current
    camRef.current = { ...cam, x: e.clientX - dragRef.current.x, y: e.clientY - dragRef.current.y }
    draw()
  }
  const onPointerUp = (e: React.PointerEvent) => {
    // A click is a pointerup that did not travel. Without the distance check,
    // panning would select whatever sat under the cursor when the drag ended.
    if (dragRef.current && movedRef.current < 5) pick(e.clientX, e.clientY)
    dragRef.current = null
  }

  const expandAll = () => {
    for (const n of nodesRef.current) expandedRef.current.add(n.id)
    setExpandedCount(expandedRef.current.size)
    fitTo(nodesRef.current.map(n => n.id), 60)
  }
  const collapseAll = () => {
    expandedRef.current = new Set()
    setExpandedCount(0)
    selectedRef.current = null
    setSelected(null)
    fitTo(rootsRef.current, 110, 1.0)
  }

  const connections = useMemo(() => {
    if (!selected) return []
    const out: { verb: string | null; other: string; dir: string }[] = []
    for (const e of edgesRef.current) {
      if (e.source === selected.id) out.push({ verb: e.label, other: e.target, dir: "→" })
      else if (e.target === selected.id) out.push({ verb: e.label, other: e.source, dir: "←" })
    }
    return out
  }, [selected])

  const props = useMemo(() => {
    if (!selected?.properties) return []
    return Object.entries(selected.properties)
      .filter(([, v]) => v !== null && v !== "")
      .slice(0, 14)
  }, [selected])

  const walkTo = (id: string) => {
    const nd = byIdRef.current.get(id)
    if (!nd) return
    expandedRef.current.add(nd.id)
    setExpandedCount(expandedRef.current.size)
    selectedRef.current = nd.id
    setSelected(nd)
    fitTo(neighbours(nd.id), 90, 1.25)
    wake()
  }

  const empty = !loading && !error && counts.nodes === 0

  return (
    <div className="flex h-full min-h-0 flex-col" aria-label="Knowledge graph">
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-6 py-4">
        <div className="min-w-0">
          <h1 className="text-[22px] font-semibold tracking-tight text-foreground">Knowledge graph</h1>
          <p className="mt-0.5 text-[13.5px] text-muted-foreground" id="graph-stats">
            {loading ? "Loading the graph…"
              : error ? `Could not load the graph: ${error}`
              : `${counts.nodes} nodes · ${counts.edges} edges in “${brain}”${source ? ` (${source})` : ""}`
              + (expandedCount ? ` · ${expandedCount} opened` : "")}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-1.5" role="group" aria-label="Graph controls">
          <span className="mr-1 text-[11px] tabular-nums text-muted-foreground" data-zoom={zoomPct}>
            {zoomPct}%
          </span>
          <button type="button" title="Zoom in" aria-label="Zoom in"
                  onClick={() => zoomAt(sizeRef.current.w / 2, sizeRef.current.h / 2, 1.25)}
                  className="h-8 w-8 rounded-lg border border-border bg-card text-base leading-none text-foreground hover:border-accent">+</button>
          <button type="button" title="Zoom out" aria-label="Zoom out"
                  onClick={() => zoomAt(sizeRef.current.w / 2, sizeRef.current.h / 2, 0.8)}
                  className="h-8 w-8 rounded-lg border border-border bg-card text-base leading-none text-foreground hover:border-accent">−</button>
          <button type="button" title="Reset view" aria-label="Reset view" onClick={collapseAll}
                  className="h-8 rounded-lg border border-border bg-card px-2 text-xs text-foreground hover:border-accent">Fit</button>
          <button type="button" title="Expand everything" aria-label="Expand everything" onClick={expandAll}
                  className="h-8 rounded-lg border border-border bg-card px-2 text-xs text-foreground hover:border-accent">Expand all</button>
          <button type="button" title="Collapse to core nodes" aria-label="Collapse to core nodes" onClick={collapseAll}
                  className="h-8 rounded-lg border border-border bg-card px-2 text-xs text-foreground hover:border-accent">Collapse</button>
        </div>
      </header>

      <div className="relative min-h-0 flex-1">
        <div ref={wrapRef} className="absolute inset-0">
          <canvas
            ref={canvasRef}
            className="h-full w-full cursor-grab touch-none active:cursor-grabbing"
            role="img"
            aria-label={`Graph of ${brain}: ${counts.nodes} nodes, ${counts.edges} edges. Click a node to open its sub-nodes.`}
            onWheel={onWheel}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerLeave={() => { dragRef.current = null }}
          />
        </div>

        {!loading && !error && legend.length > 0 && (
          <ul className="absolute right-4 top-4 rounded-xl border border-border bg-card/95 px-3.5 py-2.5 text-[11px] text-muted-foreground backdrop-blur"
              aria-label="Node types">
            {legend.map(l => (
              <li key={l.type} className="flex items-center gap-2 py-0.5">
                <span className="h-2.5 w-2.5 rounded-full" aria-hidden
                      style={{ background: typeColorRef.current[l.type] || palRef.current.colors[0] }} />
                <span className="text-foreground">{l.type}</span>
                <span>{l.n}</span>
              </li>
            ))}
          </ul>
        )}

        {empty && (
          <p className="absolute inset-x-0 top-1/2 mx-auto max-w-md -translate-y-1/2 rounded-xl border border-border bg-card p-5 text-center text-sm text-muted-foreground">
            This brain&rsquo;s graph is empty. Create a brain and add documents — the
            graph builds as files are ingested.
          </p>
        )}

        {!loading && !error && core.length > 0 && (
          <div className="absolute bottom-9 left-4 max-w-[70%]">
            <div className="mb-1.5 text-[10.5px] uppercase tracking-wide text-muted-foreground">
              Core nodes
            </div>
            <div className="flex flex-wrap gap-1.5">
              {core.map(n => (
                <button key={n.id} type="button" onClick={() => walkTo(n.id)}
                        aria-label={`Open ${n.label}`}
                        className="inline-flex max-w-[180px] items-center gap-1.5 rounded-full border border-border bg-card/95 px-2.5 py-1 text-[11px] text-foreground backdrop-blur hover:border-accent">
                  <span className="h-2 w-2 shrink-0 rounded-full" aria-hidden
                        style={{ background: typeColorRef.current[n.type] || palRef.current.colors[0] }} />
                  <span className="truncate">{n.label}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {!loading && !error && counts.nodes > 0 && (
          <p className="pointer-events-none absolute bottom-3 left-1/2 -translate-x-1/2 text-[11px] text-muted-foreground">
            click a node to open its sub-nodes · scroll to zoom · drag to pan
          </p>
        )}

        {selected && (
          <aside className="absolute inset-y-0 left-0 flex w-[min(360px,85%)] flex-col border-r border-border bg-card"
                 aria-label="Node details">
            <div className="flex items-start gap-2 border-b border-border px-4 py-3">
              <div className="min-w-0">
                <div className="text-[10.5px] uppercase tracking-wide text-accent">{selected.type}</div>
                <h2 className="mt-0.5 truncate text-sm font-semibold text-foreground" title={selected.label}>
                  {selected.label}
                </h2>
              </div>
              <button type="button" aria-label="Close" className="ml-auto rounded-md border border-border px-2 text-muted-foreground hover:text-foreground"
                      onClick={() => { selectedRef.current = null; setSelected(null); wake() }}>×</button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
              {props.length > 0 && (
                <>
                  <div className="mb-2 mt-1 text-[10.5px] uppercase tracking-wide text-muted-foreground">Properties</div>
                  <dl className="space-y-1 text-[11.5px]">
                    {props.map(([k, v]) => {
                      const full = typeof v === "object" ? JSON.stringify(v) : String(v)
                      return (
                        <div key={k} className="flex gap-2 border-b border-line pb-1">
                          <dt className="min-w-[92px] shrink-0 text-muted-foreground">{k}</dt>
                          <dd className="break-words text-foreground" title={full}>
                            {full.length > 420 ? full.slice(0, 420) + "…" : full}
                          </dd>
                        </div>
                      )
                    })}
                  </dl>
                </>
              )}
              <div className="mb-2 mt-4 text-[10.5px] uppercase tracking-wide text-muted-foreground">
                Connections ({connections.length})
              </div>
              {connections.length === 0 ? (
                <p className="text-[11.5px] text-muted-foreground">No relationships.</p>
              ) : (
                <ul className="space-y-1">
                  {connections.slice(0, 60).map((l, i) => {
                    const other = byIdRef.current.get(l.other)
                    return (
                      <li key={l.other + i}>
                        <button type="button" onClick={() => walkTo(l.other)}
                                className="flex w-full items-center gap-2 rounded-lg border border-border px-2 py-1.5 text-left text-[11.5px] hover:border-accent">
                          <span className="shrink-0 text-accent" aria-hidden>{l.dir}</span>
                          <span className="shrink-0 text-muted-foreground">{l.verb || "related"}</span>
                          <span className="truncate text-foreground">{other?.label || l.other}</span>
                        </button>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          </aside>
        )}
      </div>
    </div>
  )
}
