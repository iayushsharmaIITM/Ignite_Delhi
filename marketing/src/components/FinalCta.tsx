import { StageBadge } from "@/components/Logo"
import { CONTACT_MAILTO, CONTACT_EMAIL } from "@/contact"

export function FinalCta() {
  return (
    <section aria-labelledby="cta-heading" className="relative overflow-hidden border-t border-line">
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-1/2 h-[480px] w-[720px] -translate-x-1/2 -translate-y-1/2 rounded-full opacity-80"
        style={{
          background:
            "radial-gradient(ellipse, rgba(232,134,59,0.13) 0%, rgba(232,134,59,0.04) 45%, transparent 70%)",
        }}
      />
      <div className="reveal relative mx-auto max-w-3xl px-5 py-24 text-center lg:py-32">
        <StageBadge />
        <h2
          id="cta-heading"
          className="mt-5 text-balance text-[32px] font-semibold tracking-[-0.02em] text-ink sm:text-[44px]"
        >
          Give your company's knowledge a place to connect.
        </h2>
        <p className="mx-auto mt-4 max-w-[52ch] text-[15.5px] leading-relaxed text-muted">
          Early access is invite-based while Kestrel is in development. Send us
          a note and we'll reply from{" "}
          <span className="text-ink-2">{CONTACT_EMAIL}</span> about the next
          beta round.
        </p>
        <a
          href={CONTACT_MAILTO}
          className="mt-8 inline-block rounded-full bg-accent px-8 py-3.5 text-[15.5px] font-semibold text-accent-ink shadow-[0_0_32px_rgba(232,134,59,0.35)] transition-[transform,box-shadow] hover:-translate-y-px hover:shadow-[0_0_44px_rgba(232,134,59,0.5)]"
        >
          Request early access
        </a>
        <p className="mt-5 text-[12px] text-muted">
          This opens your email client — there is no form to fill in yet.
        </p>
      </div>
    </section>
  )
}
