import { useEffect } from "react"
import { Nav } from "@/components/Nav"
import { Hero } from "@/components/Hero"
import { Demo } from "@/components/Demo"
import { HowItWorks } from "@/components/HowItWorks"
import { Features } from "@/components/Features"
import { UseCases } from "@/components/UseCases"
import { Faq } from "@/components/Faq"
import { FinalCta } from "@/components/FinalCta"
import { Footer } from "@/components/Footer"

/**
 * Scroll-reveal, run AFTER React commits so every .reveal element exists
 * when the observer attaches. The hiding class is only added once JS is
 * confirmed running AND motion is allowed — without JS (or with
 * prefers-reduced-motion) content is fully visible, never trapped behind
 * an animation gate.
 */
function useRevealOnScroll() {
  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    if (reduced || !("IntersectionObserver" in window)) return

    const html = document.documentElement
    html.classList.add("reveal-ready")

    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add("is-visible")
            io.unobserve(e.target)
          }
        }
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 },
    )
    document.querySelectorAll(".reveal").forEach((el) => io.observe(el))

    // Safety net: even if something goes wrong with the observer, nothing
    // stays hidden — reveal everything after a short grace period.
    const failsafe = window.setTimeout(() => {
      document.querySelectorAll(".reveal:not(.is-visible)").forEach((el) => {
        const r = el.getBoundingClientRect()
        if (r.top < window.innerHeight) el.classList.add("is-visible")
      })
    }, 1200)

    return () => {
      io.disconnect()
      window.clearTimeout(failsafe)
      html.classList.remove("reveal-ready")
    }
  }, [])
}

export default function App() {
  useRevealOnScroll()
  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-lg focus:bg-accent focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-accent-ink"
      >
        Skip to content
      </a>
      <Nav />
      <main id="main">
        <Hero />
        <Demo />
        <HowItWorks />
        <Features />
        <UseCases />
        <Faq />
        <FinalCta />
      </main>
      <Footer />
    </>
  )
}
