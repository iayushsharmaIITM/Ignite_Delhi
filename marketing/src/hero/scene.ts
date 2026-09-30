import * as THREE from "three"

/**
 * The signature hero scene, drawn with raw three.js (no reconciler layer —
 * one imperative scene, one render loop, full control over pausing).
 *
 * Composition, looping through three stages over ~14s:
 *   A — document cards drift as scattered knowledge
 *   B — dashed connection lines flow from the cards toward the centre
 *   C — a readable answer card with three source references fades in
 *
 * Lifecycle contract with the caller:
 *   - mount() returns a cleanup fn
 *   - rendering pauses when the canvas leaves the viewport or the tab hides
 *   - onFirstFrame fires once the scene has actually drawn, so the host can
 *     cross-fade from the static SVG fallback
 */

type MountOpts = {
  pointerFine: boolean
  onFirstFrame: () => void
}

const ORANGE = 0xe8873a
const ORANGE_HI = 0xf49d54
const BG = 0x141414

/** Synthetic corpus titles — same fixture family as the app's demo brain. */
const DOCS = [
  "MSA · Bluepeak",
  "Ticket #4412",
  "Meeting · Aug 14",
  "SLA credit policy",
  "QBR · Aug 28",
  "On-call handbook",
]

function docTexture(title: string): THREE.CanvasTexture {
  const c = document.createElement("canvas")
  c.width = 256
  c.height = 176
  const ctx = c.getContext("2d")!
  ctx.fillStyle = "#212121"
  ctx.fillRect(0, 0, 256, 176)
  ctx.strokeStyle = "#3a3a3a"
  ctx.lineWidth = 2
  ctx.strokeRect(1, 1, 254, 174)
  ctx.fillStyle = "#e8873a"
  ctx.beginPath()
  ctx.roundRect(20, 22, 44, 8, 4)
  ctx.fill()
  ctx.fillStyle = "#f2f0ec"
  ctx.font = '600 19px "Inter Variable", sans-serif'
  ctx.fillText(title, 20, 62, 216)
  ctx.fillStyle = "#3a3a3a"
  ;[200, 160, 186, 120].forEach((w, i) => {
    ctx.beginPath()
    ctx.roundRect(20, 84 + i * 20, w, 8, 4)
    ctx.fill()
  })
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 4
  return tex
}

function answerTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas")
  c.width = 512
  c.height = 300
  const ctx = c.getContext("2d")!
  ctx.fillStyle = "#212121"
  ctx.fillRect(0, 0, 512, 300)
  ctx.strokeStyle = "#3a3a3a"
  ctx.lineWidth = 2
  ctx.strokeRect(1, 1, 510, 298)
  ctx.fillStyle = "#f2f0ec"
  ctx.font = '600 24px "Inter Variable", sans-serif'
  ctx.fillText("Why is the Bluepeak renewal at risk?", 28, 52, 456)
  ctx.fillStyle = "#4a4a4a"
  ;[420, 380, 440, 300].forEach((w, i) => {
    ctx.beginPath()
    ctx.roundRect(28, 78 + i * 26, w, 10, 5)
    ctx.fill()
  })
  ;["1", "2", "3"].forEach((n, i) => {
    const x = 28 + i * 56
    ctx.strokeStyle = "#e8873a"
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.roundRect(x, 220, 44, 32, 16)
    ctx.stroke()
    ctx.fillStyle = "#e8873a"
    ctx.font = '600 16px "Inter Variable", sans-serif'
    ctx.fillText(n, x + 19, 241)
  })
  ctx.fillStyle = "#a8a49d"
  ctx.font = '13px "Inter Variable", sans-serif'
  ctx.fillText("3 sources cited", 28, 278)
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 4
  return tex
}

const ease = (t: number) => t * t * (3 - 2 * t)
const span = (t: number, a: number, b: number) => ease(Math.min(1, Math.max(0, (t - a) / (b - a))))

export function mount(container: HTMLElement, opts: MountOpts): () => void {
  const disposed: Array<() => void> = []
  const geometry: Array<THREE.BufferGeometry> = []
  const materials: Array<THREE.Material> = []
  const textures: Array<THREE.Texture> = []

  let renderer: THREE.WebGLRenderer
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  } catch {
    throw new Error("WebGL unavailable")
  }
  const cores = navigator.hardwareConcurrency ?? 8
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, cores <= 4 ? 1.25 : 2))
  renderer.setClearColor(BG, 0)
  container.appendChild(renderer.domElement)
  renderer.domElement.setAttribute("aria-hidden", "true")

  const scene = new THREE.Scene()
  scene.fog = new THREE.Fog(BG, 9, 17)
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 40)
  camera.position.set(0, 0.55, 9.6)
  camera.lookAt(0, 0.1, 0)

  scene.add(new THREE.AmbientLight(0xffffff, 0.55))
  const key = new THREE.DirectionalLight(0xfff1e0, 1.15)
  key.position.set(4.5, 6, 6)
  scene.add(key)
  const glow = new THREE.PointLight(ORANGE, 26, 18, 1.9)
  glow.position.set(-4.5, -1.5, 4)
  scene.add(glow)
  const fill = new THREE.DirectionalLight(0xffffff, 0.4)
  fill.position.set(-5, 2, 6)
  scene.add(fill)

  const root = new THREE.Group()
  scene.add(root)

  // ---- diamond core -------------------------------------------------------
  const coreGeo = new THREE.OctahedronGeometry(1.02)
  geometry.push(coreGeo)
  const coreMat = new THREE.MeshStandardMaterial({
    color: ORANGE,
    emissive: 0x7a4416,
    emissiveIntensity: 0.85,
    metalness: 0.35,
    roughness: 0.28,
  })
  materials.push(coreMat)
  const core = new THREE.Mesh(coreGeo, coreMat)
  root.add(core)

  const cageGeo = new THREE.OctahedronGeometry(1.34)
  geometry.push(cageGeo)
  const cageMat = new THREE.MeshBasicMaterial({
    color: ORANGE_HI,
    wireframe: true,
    transparent: true,
    opacity: 0.22,
  })
  materials.push(cageMat)
  const cage = new THREE.Mesh(cageGeo, cageMat)
  root.add(cage)

  // ---- document cards ------------------------------------------------------
  const cardGeo = new THREE.BoxGeometry(1.5, 1.04, 0.07)
  geometry.push(cardGeo)
  const angles = [-152, -95, -18, 32, 92, 148].map((d) => (d * Math.PI) / 180)
  const cards: Array<{ mesh: THREE.Mesh; home: THREE.Vector3; bob: number }> = []
  DOCS.forEach((title, i) => {
    const tex = docTexture(title)
    textures.push(tex)
    const mat = new THREE.MeshStandardMaterial({
      map: tex,
      roughness: 0.62,
      metalness: 0.08,
    })
    materials.push(mat)
    const mesh = new THREE.Mesh(cardGeo, mat)
    const a = angles[i]
    const r = 3.5 + (i % 2) * 0.55
    const home = new THREE.Vector3(Math.cos(a) * r, (i - 2.5) * 0.7, Math.sin(a) * r * 0.3)
    mesh.position.copy(home)
    // Face the viewer (camera sits far on +Z) with a gentle inward tilt —
    // facing the core instead would show most cards edge-on.
    mesh.rotation.set(
      THREE.MathUtils.clamp(home.y * 0.06, -0.2, 0.2),
      THREE.MathUtils.clamp(-home.x * 0.1, -0.35, 0.35),
      0,
    )
    cards.push({ mesh, home, bob: Math.random() * Math.PI * 2 })
    root.add(mesh)
  })

  // ---- connection lines ------------------------------------------------------
  // Dashes "flow" card→core by shifting the lineDistance attribute: the
  // dashed-material shader discards where mod(distance, dash+gap) lands in
  // the gap, so offsetting every distance slides the pattern along the line.
  const lines: Array<{
    line: THREE.Line
    base: Float32Array
    attr: THREE.BufferAttribute
    mat: THREE.LineDashedMaterial
  }> = []
  cards.forEach(({ home }) => {
    const pts: THREE.Vector3[] = []
    const N = 24
    for (let i = 0; i <= N; i++) {
      const p = home.clone().lerp(new THREE.Vector3(0, 0, 0), ease(i / N))
      p.y += Math.sin((i / N) * Math.PI) * -0.18
      pts.push(p)
    }
    const geo = new THREE.BufferGeometry().setFromPoints(pts)
    geometry.push(geo)
    const mat = new THREE.LineDashedMaterial({
      color: ORANGE,
      dashSize: 0.16,
      gapSize: 0.1,
      transparent: true,
      opacity: 0,
    })
    materials.push(mat)
    const line = new THREE.Line(geo, mat)
    line.computeLineDistances()
    const attr = line.geometry.getAttribute("lineDistance") as THREE.BufferAttribute
    lines.push({ line, base: Float32Array.from(attr.array as ArrayLike<number>), attr, mat })
    root.add(line)
  })

  // ---- answer card -----------------------------------------------------------
  const ansTex = answerTexture()
  textures.push(ansTex)
  const ansGeo = new THREE.PlaneGeometry(2.9, 1.7)
  geometry.push(ansGeo)
  const ansMat = new THREE.MeshBasicMaterial({ map: ansTex, transparent: true, opacity: 0 })
  materials.push(ansMat)
  const answer = new THREE.Mesh(ansGeo, ansMat)
  answer.position.set(2.15, -0.35, 1.9)
  answer.rotation.y = -0.2
  answer.scale.setScalar(0.92)
  root.add(answer)

  // ---- sizing ------------------------------------------------------------------
  const resize = () => {
    const w = container.clientWidth || 1
    const h = container.clientHeight || 1
    // style must track the container — with updateStyle=false the canvas
    // stays at buffer size and the composition drifts off-frame.
    renderer.setSize(w, h)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
  }
  resize()
  const ro = new ResizeObserver(resize)
  ro.observe(container)
  disposed.push(() => ro.disconnect())

  // ---- pointer parallax (desktop, fine pointers only) ---------------------------
  let targetRY = 0
  let targetRX = 0
  const onPointer = (e: PointerEvent) => {
    const nx = (e.clientX / window.innerWidth) * 2 - 1
    const ny = (e.clientY / window.innerHeight) * 2 - 1
    targetRY = nx * 0.11
    targetRX = ny * 0.05
  }
  if (opts.pointerFine) {
    window.addEventListener("pointermove", onPointer, { passive: true })
    disposed.push(() => window.removeEventListener("pointermove", onPointer))
  }

  // ---- render loop with pause gates ----------------------------------------------
  let visible = true
  const io = new IntersectionObserver((es) => {
    visible = es.some((e) => e.isIntersecting)
  })
  io.observe(container)
  disposed.push(() => io.disconnect())

  const onVis = () => {
    if (document.hidden) visible = false
  }
  document.addEventListener("visibilitychange", onVis)
  disposed.push(() => document.removeEventListener("visibilitychange", onVis))

  const CYCLE = 14
  let first = true
  const clock = new THREE.Clock()
  let raf = 0

  const tick = () => {
    raf = requestAnimationFrame(tick)
    if (!visible) return
    const dt = Math.min(clock.getDelta(), 0.05)
    const et = clock.elapsedTime
    const t = et % CYCLE

    // stages: cards drift (always) → lines (3–6.5s) → answer (6.5–8.5s) → reset (12–14s)
    const answerIn = span(t, 6.5, 8.5)
    const reset = span(t, 12, 14)

    // Parallax target plus a small bounded sway — an accumulating orbit
    // would eventually show card backs and drift the composition off-frame.
    const ambient = Math.sin(et * 0.1) * 0.07
    root.rotation.y += (targetRY + ambient - root.rotation.y) * 0.05
    root.rotation.x += (targetRX - root.rotation.x) * 0.05

    core.rotation.y += dt * 0.5
    core.rotation.x = Math.sin(et * 0.4) * 0.12
    cage.rotation.y -= dt * 0.22
    cage.rotation.z += dt * 0.1
    const pulse = 1 + Math.sin(et * 1.6) * 0.03
    core.scale.setScalar(pulse)
    cage.scale.setScalar(pulse * (1 + answerIn * 0.05 - reset * 0.05))

    cards.forEach((c, i) => {
      const m = c.mesh
      const breathe = 1 + Math.sin((t / CYCLE) * Math.PI * 2) * 0.09
      m.position.set(
        c.home.x * breathe,
        c.home.y + Math.sin(et * 0.7 + c.bob) * 0.14,
        c.home.z * breathe,
      )
      m.rotation.z = Math.sin(et * 0.5 + c.bob) * 0.03
      const mat = lines[i].mat
      const stagger = span(t, 3 + i * 0.4, 5 + i * 0.4) * (1 - reset)
      mat.opacity = 0.55 * stagger
    })

    // dash flow: push every lineDistance forward by a shared clock
    const flow = (et * 0.9) % 10
    lines.forEach((l) => {
      if (l.mat.opacity <= 0.01) return
      const arr = l.attr.array as Float32Array
      for (let k = 0; k < arr.length; k++) arr[k] = l.base[k] + flow
      l.attr.needsUpdate = true
    })

    ansMat.opacity = answerIn * (1 - reset)
    answer.scale.setScalar(0.92 + answerIn * 0.08)
    answer.position.y = -0.35 + Math.sin(et * 0.8) * 0.05

    glow.intensity = 22 + Math.sin(et * 1.6) * 4 + answerIn * 6

    renderer.render(scene, camera)
    if (first) {
      first = false
      opts.onFirstFrame()
    }
  }
  raf = requestAnimationFrame(tick)
  disposed.push(() => cancelAnimationFrame(raf))

  return () => {
    disposed.forEach((fn) => fn())
    geometry.forEach((g) => g.dispose())
    materials.forEach((m) => m.dispose())
    textures.forEach((t) => t.dispose())
    renderer.dispose()
    renderer.domElement.remove()
  }
}
