import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";

// ─── Types ───────────────────────────────────────────────────────────────────

type GNode = {
  id: string;
  label?: string;
  type?: string;
  properties?: Record<string, unknown> | null;
};

type GEdge = {
  source: string;
  target: string;
  label?: string;
};

type GraphData = {
  nodes: GNode[];
  edges: GEdge[];
  source?: string;
};

type SimNode = Omit<GNode, "type"> & {
  type: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
};

type SimEdge = {
  source: string;
  target: string;
  label?: string;
};

type Cam = { x: number; y: number; k: number };

type Props = { brain: string };

// ─── Constants ───────────────────────────────────────────────────────────────

const PALETTE = [
  "#e9e9e9",
  "#e8863b",
  "#b9b9b9",
  "#f49d54",
  "#8f8f8f",
  "#d97706",
  "#c9c9c9",
  "#6b6b6b",
  "#a3a3a3",
  "#ef8f3d",
];

const CORE_NODE_COUNT = 12;
const MAX_VISIBLE_NODES = 120;
const LABEL_ZOOM_THRESHOLD = 0.85;
const MAX_ZOOM = 4;
const MIN_ZOOM = 0.2;

// ─── Helpers ─────────────────────────────────────────────────────────────────

function colorFor(type: string, cache: Record<string, string>): string {
  if (!(type in cache)) {
    cache[type] = PALETTE[Object.keys(cache).length % PALETTE.length];
  }
  return cache[type];
}

function labelOf(n: GNode): string {
  return (n.label || n.id || "").replace(/^([A-Za-z]+)_[0-9a-f-]{8,}$/, "$1");
}

// ─── Component ───────────────────────────────────────────────────────────────

export function GraphPage({ brain }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);

  // Simulation state (mutable, lives in refs for the rAF loop)
  const simRef = useRef<{
    nodes: SimNode[];
    edges: SimEdge[];
    byId: Map<string, SimNode>;
    cam: Cam;
    camTarget: Cam | null;
    roots: string[];
    expanded: Set<string>;
    visibleIds: Set<string>;
    selected: string | null;
    alpha: number;
    running: boolean;
    drag: { x: number; y: number } | null;
    moved: number;
    W: number;
    H: number;
    DPR: number;
    typeColorCache: Record<string, string>;
  }>({
    nodes: [],
    edges: [],
    byId: new Map(),
    cam: { x: 0, y: 0, k: 1 },
    camTarget: null,
    roots: [],
    expanded: new Set(),
    visibleIds: new Set(),
    selected: null,
    alpha: 1,
    running: false,
    drag: null,
    moved: 0,
    W: 0,
    H: 0,
    DPR: 1,
    typeColorCache: {},
  });

  // UI state
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<SimNode | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [legend, setLegend] = useState<{ type: string; count: number; color: string }[]>([]);
  const [stats, setStats] = useState({ nodes: 0, edges: 0 });
  const [truncated, setTruncated] = useState(false);
  const [exitVisible, setExitVisible] = useState(false);

  // ── Data fetching ──────────────────────────────────────────────────────────

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSelectedNode(null);
    setInspectorOpen(false);
    setExitVisible(false);

    apiFetch(`/api/graph?brain=${encodeURIComponent(brain)}`)
      .then((r) => {
        if (!r.ok) {
          if (r.status === 401 || r.status === 403) {
            throw new Error(`Sign in to view this graph (HTTP ${r.status})`);
          }
          throw new Error(`HTTP ${r.status}`);
        }
        return r.json();
      })
      .then((g: GraphData & { error?: string }) => {
        if (cancelled) return;
        if (g.error) throw new Error(g.error);

        const rawNodes = g.nodes || [];
        const rawEdges = g.edges || [];

        if (!rawNodes.length) {
          setLoading(false);
          return;
        }

        const sim = simRef.current;
        const { W, H } = sim;

        // Build simulation nodes
        const nodes: SimNode[] = rawNodes.map((n, i) => {
          const type = n.type || "Node";
          const lbl = labelOf(n);
          return {
            ...n,
            type,
            label: lbl,
            properties: n.properties || null,
            r: 4 + Math.min(7, (lbl.length || 0) / 8),
            x: W / 2 + Math.cos(i * 2.399) * (60 + Math.random() * 220),
            y: H / 2 + Math.sin(i * 2.399) * (60 + Math.random() * 220),
            vx: 0,
            vy: 0,
          };
        });

        const byId = new Map<string, SimNode>();
        nodes.forEach((n) => byId.set(n.id, n));

        const ids = new Set(nodes.map((n) => n.id));
        const edges: SimEdge[] = rawEdges
          .map((e) => ({
            source: e.source ?? (e as unknown as { from?: string }).from ?? "",
            target: e.target ?? (e as unknown as { to?: string }).to ?? "",
            label: e.label ?? (e as unknown as { type?: string }).type ?? undefined,
          }))
          .filter((e) => ids.has(e.source) && ids.has(e.target));

        // Truncation: if > MAX_VISIBLE_NODES, keep the most-connected ones
        let truncatedIds: Set<string> | null = null;
        if (nodes.length > MAX_VISIBLE_NODES) {
          truncatedIds = new Set();
          // Keep the top MAX_VISIBLE_NODES by degree
          const degree = new Map<string, number>();
          edges.forEach((e) => {
            degree.set(e.source, (degree.get(e.source) || 0) + 1);
            degree.set(e.target, (degree.get(e.target) || 0) + 1);
          });
          const sorted = [...nodes].sort(
            (a, b) => (degree.get(b.id) || 0) - (degree.get(a.id) || 0)
          );
          sorted.slice(0, MAX_VISIBLE_NODES).forEach((n) => truncatedIds!.add(n.id));
          setTruncated(true);
        } else {
          setTruncated(false);
        }

        // Filter to visible nodes
        const visibleNodes = truncatedIds
          ? nodes.filter((n) => truncatedIds!.has(n.id))
          : nodes;
        const visibleIdsSet = new Set(visibleNodes.map((n) => n.id));
        const visibleEdges = edges.filter(
          (e) => visibleIdsSet.has(e.source) && visibleIdsSet.has(e.target)
        );

        // Compute core nodes (most connected)
        const degree = new Map<string, number>();
        visibleEdges.forEach((e) => {
          degree.set(e.source, (degree.get(e.source) || 0) + 1);
          degree.set(e.target, (degree.get(e.target) || 0) + 1);
        });
        const roots = [...visibleNodes]
          .map((n) => ({ id: n.id, deg: degree.get(n.id) || 0 }))
          .sort((a, b) => b.deg - a.deg)
          .slice(0, CORE_NODE_COUNT)
          .map((x) => x.id);

        // Legend
        const typeCounts: Record<string, number> = {};
        visibleNodes.forEach((n) => {
          typeCounts[n.type] = (typeCounts[n.type] || 0) + 1;
        });
        const legendData = Object.entries(typeCounts)
          .sort((a, b) => b[1] - a[1])
          .map(([type, count]) => ({
            type,
            count,
            color: colorFor(type, sim.typeColorCache),
          }));

        // Update sim state
        sim.nodes = visibleNodes;
        sim.edges = visibleEdges;
        sim.byId = new Map(visibleNodes.map((n) => [n.id, n]));
        sim.roots = roots;
        sim.expanded = new Set();
        sim.visibleIds = new Set(roots);
        sim.selected = null;
        sim.alpha = 1;
        sim.cam = { x: 0, y: 0, k: 1 };
        sim.camTarget = null;

        setLegend(legendData);
        setStats({ nodes: visibleNodes.length, edges: visibleEdges.length });
        setLoading(false);

        // Fit to roots
        fitTo(roots, 110, 1.0);
        wake();
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        const msg = e instanceof Error ? e.message : "unknown error";
        setError(msg);
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [brain]);

  // ── Canvas resize ──────────────────────────────────────────────────────────

  useEffect(() => {
    const canvas = canvasRef.current;
    const overlay = overlayRef.current;
    if (!canvas || !overlay) return;

    const resize = () => {
      const sim = simRef.current;
      sim.DPR = window.devicePixelRatio || 1;
      sim.W = canvas.clientWidth;
      sim.H = canvas.clientHeight;
      canvas.width = sim.W * sim.DPR;
      canvas.height = sim.H * sim.DPR;
      overlay.width = sim.W * sim.DPR;
      overlay.height = sim.H * sim.DPR;
      const ctx = canvas.getContext("2d");
      const octx = overlay.getContext("2d");
      ctx?.setTransform(sim.DPR, 0, 0, sim.DPR, 0, 0);
      octx?.setTransform(sim.DPR, 0, 0, sim.DPR, 0, 0);
    };

    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);

  // ── Force simulation ───────────────────────────────────────────────────────

  const simulate = useCallback((alpha: number) => {
    const sim = simRef.current;
    const { nodes, edges, byId, W, H } = sim;
    const cx = W / 2;
    const cy = H / 2;

    // Centering + velocity decay
    for (const n of nodes) {
      n.vx = (n.vx || 0) * 0.86;
      n.vy = (n.vy || 0) * 0.86;
      n.vx += (cx - n.x) * 0.0009 * alpha;
      n.vy += (cy - n.y) * 0.0009 * alpha;
    }

    // Repulsion
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i];
        const b = nodes[j];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const d2 = dx * dx + dy * dy || 1;
        if (d2 > 160000) continue;
        const f = 1500 / d2;
        const d = Math.sqrt(d2);
        const nx = dx / d;
        const ny = dy / d;
        a.vx -= nx * f * alpha;
        a.vy -= ny * f * alpha;
        b.vx += nx * f * alpha;
        b.vy += ny * f * alpha;
      }
    }

    // Springs
    for (const e of edges) {
      const a = byId.get(e.source);
      const b = byId.get(e.target);
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const f = (d - 135) * 0.012 * alpha;
      const ux = dx / d;
      const uy = dy / d;
      a.vx += ux * f;
      a.vy += uy * f;
      b.vx -= ux * f;
      b.vy -= uy * f;
    }

    for (const n of nodes) {
      n.x += n.vx;
      n.y += n.vy;
    }
  }, []);

  // ── Camera easing ──────────────────────────────────────────────────────────

  const easeCam = useCallback((): boolean => {
    const sim = simRef.current;
    const { cam, camTarget } = sim;
    if (!camTarget) return false;
    const t = 0.16;
    cam.x += (camTarget.x - cam.x) * t;
    cam.y += (camTarget.y - cam.y) * t;
    cam.k += (camTarget.k - cam.k) * t;
    if (
      Math.abs(camTarget.x - cam.x) < 0.6 &&
      Math.abs(camTarget.y - cam.y) < 0.6 &&
      Math.abs(camTarget.k - cam.k) < 0.002
    ) {
      sim.cam = { ...camTarget };
      sim.camTarget = null;
      return false;
    }
    return true;
  }, []);

  // ── Fit to nodes ───────────────────────────────────────────────────────────

  const fitTo = useCallback((ids: string[], pad: number, maxK: number) => {
    const sim = simRef.current;
    const { byId, W, H } = sim;
    let minX = Infinity,
      minY = Infinity,
      maxX = -Infinity,
      maxY = -Infinity,
      any = false;
    for (const id of ids) {
      const nd = byId.get(id);
      if (!nd) continue;
      any = true;
      minX = Math.min(minX, nd.x);
      maxX = Math.max(maxX, nd.x);
      minY = Math.min(minY, nd.y);
      maxY = Math.max(maxY, nd.y);
    }
    if (!any) return;
    const w = Math.max(maxX - minX, 1);
    const h = Math.max(maxY - minY, 1);
    const k = Math.min(
      maxK,
      Math.max(0.3, Math.min((W - pad * 2) / w, (H - pad * 2) / h))
    );
    sim.camTarget = {
      k,
      x: W / 2 - ((minX + maxX) / 2) * k,
      y: H / 2 - ((minY + maxY) / 2) * k,
    };
    wake();
  }, []);

  // ── Wake / render loop ─────────────────────────────────────────────────────

  const wake = useCallback(() => {
    const sim = simRef.current;
    if (!sim.running) {
      sim.running = true;
      requestAnimationFrame(frame);
    }
  }, []);

  const frame = useCallback(() => {
    const sim = simRef.current;
    const settling = sim.alpha > 0.02;
    if (settling) {
      simulate(sim.alpha);
      sim.alpha *= 0.99;
    }
    const easing = easeCam();
    draw();
    if (settling || easing) {
      requestAnimationFrame(frame);
    } else {
      sim.running = false;
    }
  }, [simulate, easeCam]);

  // ── Neighbours ─────────────────────────────────────────────────────────────

  const neighboursOf = useCallback(
    (id: string, edges: SimEdge[]): Set<string> => {
      const out = new Set([id]);
      for (const e of edges) {
        if (e.source === id && e.target) out.add(e.target);
        else if (e.target === id && e.source) out.add(e.source);
      }
      return out;
    },
    []
  );

  // ── Draw layer ─────────────────────────────────────────────────────────────

  const drawLayer = useCallback(
    (
      target: CanvasRenderingContext2D,
      wanted: (id: string) => boolean,
      cam: Cam,
      nodes: SimNode[],
      edges: SimEdge[],
      byId: Map<string, SimNode>,
      visibleIds: Set<string>,
      selected: string | null,
      typeColorCache: Record<string, string>,
      _W: number,
      _H: number
    ) => {
      target.save();
      target.translate(cam.x, cam.y);
      target.scale(cam.k, cam.k);

      // Edges
      target.globalAlpha = 1;
      target.strokeStyle = "rgba(255,255,255,.30)";
      target.lineWidth = 1.7 / cam.k;
      for (const e of edges) {
        if (!visibleIds.has(e.source) || !visibleIds.has(e.target)) continue;
        if (!(wanted(e.source) || wanted(e.target))) continue;
        const a = byId.get(e.source);
        const b = byId.get(e.target);
        if (!a || !b) continue;
        target.beginPath();
        target.moveTo(a.x, a.y);
        target.lineTo(b.x, b.y);
        target.stroke();
      }

      // Nodes
      for (const nd of nodes) {
        if (!visibleIds.has(nd.id) || !wanted(nd.id)) continue;
        const isSel = nd.id === selected;
        target.beginPath();
        target.arc(nd.x, nd.y, isSel ? nd.r * 1.7 : nd.r, 0, Math.PI * 2);
        target.fillStyle = colorFor(nd.type, typeColorCache);
        target.fill();
        if (isSel) {
          target.strokeStyle = "#e8863b";
          target.lineWidth = 2 / cam.k;
          target.stroke();
        }
      }

      // Labels
      target.font = "11px -apple-system,sans-serif";
      target.textAlign = "center";
      for (const nd of nodes) {
        if (!visibleIds.has(nd.id) || !wanted(nd.id)) continue;
        const isSel = nd.id === selected;
        if (!isSel && cam.k <= LABEL_ZOOM_THRESHOLD) continue;
        if ((nd.label || "").length > 34) continue;
        target.fillStyle = isSel ? "#e8863b" : "rgba(255,255,255,.55)";
        target.fillText(nd.label || "", nd.x, nd.y - nd.r - 5);
      }

      target.restore();
    },
    []
  );

  const draw = useCallback(() => {
    const sim = simRef.current;
    const canvas = canvasRef.current;
    const overlay = overlayRef.current;
    if (!canvas || !overlay) return;
    const ctx = canvas.getContext("2d");
    const octx = overlay.getContext("2d");
    if (!ctx || !octx) return;

    const { W, H, cam, nodes, edges, byId, selected, typeColorCache } = sim;

    ctx.clearRect(0, 0, W, H);
    octx.clearRect(0, 0, W, H);

    // Compute visible nodes
    const vis = new Set(sim.roots);
    for (const id of sim.expanded) {
      vis.add(id);
      for (const e of edges) {
        if (e.source === id) vis.add(e.target);
        else if (e.target === id) vis.add(e.source);
      }
    }
    sim.visibleIds = vis;

    // Focus gradient
    const focus = selected ? neighboursOf(selected, edges) : null;
    const blurring = !!(focus && focus.size > 1);
    const isFocused = (id: string) => !focus || focus.has(id);

    if (blurring) {
      const sel = byId.get(selected!);
      if (sel) {
        const cx = cam.x + sel.x * cam.k;
        const cy = cam.y + sel.y * cam.k;
        const radius = Math.max(W, H) * 0.66;
        const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
        grad.addColorStop(0, "#242424");
        grad.addColorStop(0.5, "#1c1c1c");
        grad.addColorStop(1, "#141414");
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, W, H);
      }
      drawLayer(octx, isFocused, cam, nodes, edges, byId, vis, selected, typeColorCache, W, H);
    } else {
      drawLayer(ctx, () => true, cam, nodes, edges, byId, vis, selected, typeColorCache, W, H);
    }
  }, [neighboursOf, drawLayer]);

  // ── Interaction ────────────────────────────────────────────────────────────

  // Mouse down
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    const sim = simRef.current;
    sim.drag = { x: e.clientX - sim.cam.x, y: e.clientY - sim.cam.y };
    sim.moved = 0;
  }, []);

  // Mouse up (click detection)
  const handleMouseUp = useCallback(
    (e: React.MouseEvent) => {
      const sim = simRef.current;
      if (sim.drag && sim.moved < 5) {
        pick(e.clientX, e.clientY);
      }
      sim.drag = null;
    },
    []
  );

  // Mouse move (pan)
  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    const sim = simRef.current;
    if (!sim.drag) return;
    sim.moved += Math.abs(e.movementX || 0) + Math.abs(e.movementY || 0);
    sim.cam.x = e.clientX - sim.drag.x;
    sim.cam.y = e.clientY - sim.drag.y;
    // Repaint without restarting the sim loop
    if (!sim.running) draw();
  }, [draw]);

  // Zoom toward pointer
  const zoomAt = useCallback((px: number, py: number, factor: number) => {
    const sim = simRef.current;
    const k2 = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, sim.cam.k * factor));
    sim.cam.x = px - (px - sim.cam.x) * (k2 / sim.cam.k);
    sim.cam.y = py - (py - sim.cam.y) * (k2 / sim.cam.k);
    sim.cam.k = k2;
    if (!sim.running) draw();
  }, [draw]);

  // Wheel (zoom toward pointer)
  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;
      const factor = e.deltaY > 0 ? 0.92 : 1.08;
      zoomAt(px, py, factor);
    },
    [zoomAt]
  );

  // Select node
  const select = useCallback(
    (id: string | null) => {
      const sim = simRef.current;
      if (id && sim.visibleIds.has(id)) {
        if (sim.expanded.has(id)) {
          sim.expanded.delete(id);
          // Zoom back out
          const vis = new Set(sim.roots);
          for (const eid of sim.expanded) {
            vis.add(eid);
            for (const e of sim.edges) {
              if (e.source === eid) vis.add(e.target);
              else if (e.target === eid) vis.add(e.source);
            }
          }
          fitTo([...vis], 110, 1.0);
        } else {
          sim.expanded.add(id);
          const focus = new Set([id, ...neighboursOf(id, sim.edges)]);
          fitTo([...focus], 110, 1.5);
        }
      }
      sim.selected = id;
      setExitVisible(sim.expanded.size > 0 || !!id);

      if (id && sim.byId.get(id)) {
        setSelectedNode(sim.byId.get(id)!);
        setInspectorOpen(true);
      } else {
        setSelectedNode(null);
        setInspectorOpen(false);
      }
      if (!sim.running) draw();
    },
    [fitTo, neighboursOf, draw]
  );

  // Pick node at world coords
  const pick = useCallback(
    (clientX: number, clientY: number) => {
      const sim = simRef.current;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const wx = (clientX - rect.left - sim.cam.x) / sim.cam.k;
      const wy = (clientY - rect.top - sim.cam.y) / sim.cam.k;

      let hit: SimNode | null = null;
      let best = Infinity;
      for (const n of sim.nodes) {
        const d = Math.hypot(n.x - wx, n.y - wy);
        if (d <= n.r + 4 / sim.cam.k && d < best) {
          best = d;
          hit = n;
        }
      }
      select(hit ? hit.id : null);
    },
    [select]
  );

  // ── Zoom controls ──────────────────────────────────────────────────────────

  const zoomIn = useCallback(() => {
    const sim = simRef.current;
    zoomAt(sim.W / 2, sim.H / 2, 1.25);
  }, [zoomAt]);

  const zoomOut = useCallback(() => {
    const sim = simRef.current;
    zoomAt(sim.W / 2, sim.H / 2, 0.8);
  }, [zoomAt]);

  const zoomFit = useCallback(() => {
    const sim = simRef.current;
    sim.cam = { x: 0, y: 0, k: 1 };
    sim.alpha = 1;
    wake();
  }, [wake]);

  const expandAll = useCallback(() => {
    const sim = simRef.current;
    for (const nd of sim.nodes) sim.expanded.add(nd.id);
    setExitVisible(true);
    fitTo(
      sim.nodes.map((n) => n.id),
      60,
      1.5
    );
  }, [fitTo]);

  const collapseAll = useCallback(() => {
    const sim = simRef.current;
    sim.expanded.clear();
    sim.selected = null;
    setSelectedNode(null);
    setInspectorOpen(false);
    setExitVisible(false);
    fitTo(sim.roots, 110, 1.0);
  }, [fitTo]);

  // ── Keyboard ───────────────────────────────────────────────────────────────

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") select(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [select]);

  // ── Inspector render ───────────────────────────────────────────────────────

  const inspectorContent = useMemo(() => {
    if (!selectedNode) return null;
    const node = selectedNode;
    const sim = simRef.current;

    // Properties
    const props =
      node.properties && typeof node.properties === "object"
        ? Object.entries(node.properties).filter(
            ([, v]) => v !== null && v !== ""
          )
        : [];

    // Relationships grouped by verb
    const links: { verb: string; other: string; dir: string }[] = [];
    for (const e of sim.edges) {
      if (e.source === node.id) {
        links.push({ verb: e.label || "related", other: e.target, dir: "→" });
      } else if (e.target === node.id) {
        links.push({ verb: e.label || "related", other: e.source, dir: "←" });
      }
    }

    // Group by verb
    const grouped = new Map<string, { verb: string; items: { other: string; dir: string }[] }>();
    for (const l of links) {
      if (!grouped.has(l.verb)) grouped.set(l.verb, { verb: l.verb, items: [] });
      grouped.get(l.verb)!.items.push({ other: l.other, dir: l.dir });
    }

    return { node, props, links, grouped: [...grouped.values()] };
  }, [selectedNode]);

  // ── Render ─────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="text-center">
          <div className="mb-3 inline-block h-8 w-8 animate-spin rounded-full border-2 border-line-2 border-t-accent" />
          <p className="text-sm text-muted-foreground">Loading the graph…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center p-8">
        <div className="max-w-md text-center">
          <p className="text-[15px] font-medium text-bad">
            Could not load the graph
          </p>
          <p className="mt-2 text-sm text-muted-foreground">{error}</p>
          <a
            href={`/graph?brain=${encodeURIComponent(brain)}`}
            className="mt-4 inline-block text-sm text-accent underline underline-offset-2 hover:text-accent-2"
          >
            Try the legacy graph page
          </a>
        </div>
      </div>
    );
  }

  if (stats.nodes === 0) {
    return (
      <div className="flex flex-1 items-center justify-center p-8">
        <div className="max-w-md text-center">
          <p className="text-[15px] font-medium text-foreground">
            This brain has no graph yet
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            Ingestion may still be running — check{" "}
            <a href="/brains" className="text-accent underline underline-offset-2">
              brains
            </a>
            .
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex-1 overflow-hidden">
      {/* Canvas layer */}
      <canvas
        ref={canvasRef}
        className="absolute inset-0 h-full w-full cursor-grab active:cursor-grabbing"
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onMouseMove={handleMouseMove}
        onWheel={handleWheel}
      />
      {/* Overlay layer (focus gradient) */}
      <canvas
        ref={overlayRef}
        className="pointer-events-none absolute inset-0 z-[2] h-full w-full"
      />

      {/* HUD */}
      <div className="pointer-events-none absolute left-[22px] top-5 z-10">
        <h1 className="font-serif text-[18px] font-medium tracking-tight text-foreground">
          {brain}
        </h1>
        <p className="text-[13px] text-muted-foreground">
          Entities and relationships extracted from the documents you uploaded.
        </p>
      </div>

      {/* Stats panel */}
      <div className="absolute bottom-5 left-[22px] z-10 flex items-center gap-4 rounded-[10px] border border-line-2 bg-panel px-4 py-2.5 text-[12.5px] text-muted-foreground backdrop-blur-sm">
        <span>
          <b className="font-semibold text-foreground">{stats.nodes}</b> nodes
        </span>
        <span>
          <b className="font-semibold text-foreground">{stats.edges}</b> edges
        </span>
        <span className="hidden sm:inline">click a node to open its sub-nodes</span>
        <span className="hidden sm:inline">scroll to zoom · drag to pan</span>
      </div>

      {/* Legend */}
      {legend.length > 0 && (
        <div className="absolute right-[22px] top-5 z-10 max-h-[70vh] overflow-auto rounded-[10px] border border-line-2 bg-panel px-4 py-2.5 text-[12.5px] backdrop-blur-sm">
          {legend.map((l) => (
            <div key={l.type} className="my-[3px] flex items-center gap-2 text-muted-foreground">
              <span
                className="h-[9px] w-[9px] flex-none rounded-full"
                style={{ background: l.color }}
              />
              <span>{l.type}</span>
              <span className="ml-auto pl-3 font-semibold text-foreground">{l.count}</span>
            </div>
          ))}
        </div>
      )}

      {/* Truncation notice */}
      {truncated && (
        <div className="absolute bottom-16 left-1/2 z-10 -translate-x-1/2 rounded-lg border border-line bg-panel-2 px-3 py-2 text-xs text-muted-foreground">
          Showing the {MAX_VISIBLE_NODES} most-connected of{" "}
          <b className="text-foreground">{stats.nodes}+</b> nodes for readability
          — the full interactive graph remains in the legacy view (linked below).
        </div>
      )}

      {/* Node inspector */}
      <aside
        className={`absolute bottom-0 right-0 top-0 z-30 w-[340px] overflow-y-auto border-l border-line bg-panel px-4 pb-6 pt-4 transition-transform duration-200 ease-out ${
          inspectorOpen ? "translate-x-0" : "translate-x-full"
        }`}
        aria-live="polite"
      >
        <button
          type="button"
          aria-label="Close inspector"
          onClick={() => select(null)}
          className="absolute right-3.5 top-3 flex h-7 w-7 items-center justify-center rounded-lg border border-line bg-panel-2 text-[15px] leading-none text-muted-foreground transition-colors hover:border-line-2 hover:text-foreground"
        >
          ×
        </button>

        {inspectorContent && (
          <>
            <div className="mb-2 inline-block text-[10.5px] font-bold uppercase tracking-[0.09em] text-accent">
              {inspectorContent.node.type || "node"}
            </div>
            <h2 className="mb-3.5 pr-6 text-[17px] font-semibold leading-snug break-words text-foreground">
              {inspectorContent.node.label || inspectorContent.node.id}
            </h2>

            {/* Properties */}
            {inspectorContent.props.length > 0 && (
              <>
                <div className="mb-2 mt-4 text-[10.5px] font-bold uppercase tracking-[0.1em] text-muted-2">
                  Properties
                </div>
                <div className="flex flex-col gap-[5px] text-[12.5px]">
                  {inspectorContent.props.slice(0, 14).map(([k, v]) => {
                    const full =
                      typeof v === "object" ? JSON.stringify(v) : String(v);
                    return (
                      <div key={k} className="flex gap-2">
                        <span className="min-w-[92px] flex-none text-muted-2">{k}</span>
                        <span
                          className="break-words text-foreground"
                          title={full}
                        >
                          {full.length > 420 ? full.slice(0, 420) + "…" : full}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </>
            )}

            {/* Relationships */}
            {inspectorContent.links.length === 0 ? (
              <>
                <div className="mb-2 mt-4 text-[10.5px] font-bold uppercase tracking-[0.1em] text-muted-2">
                  Connections
                </div>
                <div className="text-[12.5px] text-muted-2">No relationships.</div>
              </>
            ) : (
              <>
                <div className="mb-2 mt-4 text-[10.5px] font-bold uppercase tracking-[0.1em] text-muted-2">
                  Connections ({inspectorContent.links.length})
                </div>
                <div className="flex flex-col gap-1.5">
                  {inspectorContent.grouped.map((group) => (
                    <div key={group.verb}>
                      <div className="mb-1 mt-2 font-mono text-[11px] text-muted">
                        {group.verb}
                      </div>
                      {group.items.slice(0, 60).map((item, i) => {
                        const other = simRef.current.byId.get(item.other);
                        return (
                          <div
                            key={`${item.other}-${i}`}
                            className="flex cursor-pointer items-baseline gap-[7px] rounded-lg border border-line bg-panel-2 px-2.5 py-[7px] text-[13px] transition-colors hover:border-accent-dim"
                            onClick={() => other && select(other.id)}
                          >
                            <span className="flex-none text-[11px] text-accent">
                              {item.dir}
                            </span>
                            <span className="break-words text-foreground">
                              {other ? other.label || other.id : item.other}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </aside>

      {/* Exit node view button */}
      {exitVisible && (
        <button
          type="button"
          onClick={collapseAll}
          className="absolute bottom-[74px] right-[22px] z-32 inline-flex items-center gap-2 rounded-full border border-line-3 bg-panel-2 px-[18px] py-2.5 text-[13.5px] font-semibold text-foreground shadow-lg transition-colors hover:border-foreground hover:bg-panel-3"
          style={{ right: inspectorOpen ? 362 : 22 }}
        >
          <span className="text-[15px] leading-none text-muted-foreground">×</span>
          Exit node view
        </button>
      )}

      {/* Zoom controls */}
      <div
        className="absolute bottom-5 right-[22px] z-31 flex gap-1.5"
        style={{ right: inspectorOpen ? 362 : 22 }}
      >
        <button
          type="button"
          title="Zoom in"
          onClick={zoomIn}
          className="flex h-[34px] w-[34px] items-center justify-center rounded-[9px] border border-line bg-panel text-[15px] text-foreground transition-colors hover:border-accent-dim"
        >
          +
        </button>
        <button
          type="button"
          title="Zoom out"
          onClick={zoomOut}
          className="flex h-[34px] w-[34px] items-center justify-center rounded-[9px] border border-line bg-panel text-[15px] text-foreground transition-colors hover:border-accent-dim"
        >
          −
        </button>
        <button
          type="button"
          title="Reset view"
          onClick={zoomFit}
          className="flex h-[34px] w-[34px] items-center justify-center rounded-[9px] border border-line bg-panel text-[15px] text-foreground transition-colors hover:border-accent-dim"
        >
          ⤢
        </button>
        <button
          type="button"
          title="Expand everything"
          onClick={expandAll}
          className="flex h-[34px] w-[34px] items-center justify-center rounded-[9px] border border-line bg-panel text-[15px] text-foreground transition-colors hover:border-accent-dim"
        >
          ⊕
        </button>
        <button
          type="button"
          title="Collapse to core nodes"
          onClick={collapseAll}
          className="flex h-[34px] w-[34px] items-center justify-center rounded-[9px] border border-line bg-panel text-[15px] text-foreground transition-colors hover:border-accent-dim"
        >
          ⊖
        </button>
      </div>

      {/* Legacy link */}
      <div className="absolute bottom-5 left-1/2 z-10 -translate-x-1/2">
        <p className="text-[11.5px] text-muted-foreground">
          Full interactive graph in the{" "}
          <a
            href={`/graph?brain=${encodeURIComponent(brain)}`}
            className="text-accent underline underline-offset-2 hover:text-accent-2"
          >
            legacy view
          </a>
        </p>
      </div>
    </div>
  );
}
