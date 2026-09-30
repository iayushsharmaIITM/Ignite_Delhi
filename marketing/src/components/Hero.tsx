import { StageBadge } from "@/components/Logo"
import { Hero3D } from "@/hero/Hero3D"
import { CONTACT_MAILTO } from "@/contact"

export function Hero() {
  return (
    <section id="top" aria-labelledby="hero-heading" className="relative overflow-hidden">
      {/* controlled lighting: one warm halo behind the scene, nothing busier */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-40 right-[-10%] h-[560px] w-[560px] rounded-full opacity-70"
        style={{
          background:
            "radial-gradient(circle, rgba(232,134,59,0.14) 0%, rgba(232,134,59,0.05) 42%, transparent 68%)",
        }}
      />
      <div className="mx-auto grid max-w-6xl items-center gap-10 px-5 pb-16 pt-32 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:gap-6 lg:px-8 lg:pb-24 lg:pt-40">
        <div className="reveal">
          <StageBadge />
          <h1
            id="hero-heading"
            className="mt-5 text-balance text-[40px] font-semibold leading-[1.08] tracking-[-0.02em] text-ink sm:text-[52px] lg:text-[58px]"
          >
            Your company's knowledge.
            <br />
            <span className="text-accent">Finally connected.</span>
          </h1>
          <p className="mt-5 max-w-[52ch] text-pretty text-[16.5px] leading-relaxed text-muted">
            Bring your documents into one workspace. Ask questions, explore
            connections, and get answers grounded in your sources — with a
            citation behind every claim.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3.5">
            <a
              href={CONTACT_MAILTO}
              className="rounded-full bg-accent px-6 py-3 text-[15px] font-semibold text-accent-ink shadow-[0_0_28px_rgba(232,134,59,0.3)] transition-[transform,box-shadow] hover:-translate-y-px hover:shadow-[0_0_36px_rgba(232,134,59,0.45)]"
            >
              Request early access
            </a>
            <a
              href="#how-it-works"
              className="rounded-full border border-line-2 px-6 py-3 text-[15px] font-medium text-ink-2 transition-colors hover:border-accent hover:text-accent"
            >
              See how it works
            </a>
          </div>
          <p className="mt-6 max-w-[46ch] text-[12.5px] leading-relaxed text-muted">
            Kestrel is in active development. The walkthroughs on this page use
            synthetic example documents, not customer data.
          </p>
        </div>

        <div className="reveal relative mx-auto aspect-[560/470] w-full max-w-[640px] lg:max-w-none">
          <Hero3D />
        </div>
      </div>
    </section>
  )
}
