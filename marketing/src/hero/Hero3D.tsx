import { useEffect, useRef, useState } from "react"
import { HeroFallback } from "@/hero/HeroFallback"

/**
 * Hosts the 3D hero. The static SVG fallback is the default visual and only
 * cross-fades out once the WebGL scene has actually rendered a frame — so
 * slow networks, WebGL-less browsers and reduced-motion users all get the
 * full composition immediately, with zero content waiting on 3D.
 */
export function Hero3D() {
  const hostRef = useRef<HTMLDivElement>(null)
  const [sceneReady, setSceneReady] = useState(false)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    let webgl = false
    try {
      const probe = document.createElement("canvas")
      webgl = !!(probe.getContext("webgl2") || probe.getContext("webgl"))
    } catch {
      webgl = false
    }
    // Any of these → keep the static illustration, never mount three.
    if (reduced || !webgl) return

    let cleanup: (() => void) | undefined
    let cancelled = false
    import("@/hero/scene")
      .then((m) => {
        if (cancelled) return
        cleanup = m.mount(host, {
          pointerFine: window.matchMedia("(pointer: fine)").matches,
          onFirstFrame: () => setSceneReady(true),
        })
      })
      .catch(() => {
        /* scene failed to load — the fallback stays up */
      })
    return () => {
      cancelled = true
      cleanup?.()
    }
  }, [])

  return (
    <div className="relative h-full w-full">
      <div
        ref={hostRef}
        aria-hidden
        className={`absolute inset-0 transition-opacity duration-700 ${sceneReady ? "opacity-100" : "opacity-0"}`}
      />
      <div
        className={`absolute inset-0 transition-opacity duration-700 ${sceneReady ? "pointer-events-none opacity-0" : "opacity-100"}`}
      >
        <HeroFallback />
      </div>
    </div>
  )
}
