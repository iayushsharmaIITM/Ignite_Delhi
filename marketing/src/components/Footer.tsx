import { Logo } from "@/components/Logo"
import { CONTACT_MAILTO, CONTACT_EMAIL } from "@/contact"

const PRODUCT_LINKS = [
  { href: "#product", label: "Product" },
  { href: "#how-it-works", label: "How it works" },
  { href: "#faq", label: "FAQ" },
]

export function Footer() {
  return (
    <footer className="border-t border-line bg-bg-2">
      <div className="mx-auto grid max-w-6xl gap-10 px-5 py-14 sm:grid-cols-[1.4fr_1fr_1fr] lg:px-8">
        <div>
          <Logo />
          <p className="mt-4 max-w-[38ch] text-[13.5px] leading-relaxed text-muted">
            A company-knowledge workspace: brains of documents, plain-language
            questions, answers grounded in your own sources.
          </p>
          <p className="mt-3 text-[12px] text-muted">
            In active development. Features shown are implemented in the
            current build unless labeled "Coming soon".
          </p>
        </div>

        <nav aria-label="Footer">
          <p className="text-[11px] font-bold uppercase tracking-[0.15em] text-muted">Product</p>
          <ul className="mt-3 flex flex-col gap-2">
            {PRODUCT_LINKS.map((l) => (
              <li key={l.href}>
                <a href={l.href} className="text-[13.5px] text-ink-2 transition-colors hover:text-accent">
                  {l.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.15em] text-muted">Contact</p>
          <ul className="mt-3 flex flex-col gap-2 text-[13.5px]">
            <li>
              <a href={CONTACT_MAILTO} className="text-ink-2 transition-colors hover:text-accent">
                {CONTACT_EMAIL}
              </a>
            </li>
            <li>
              <a href={CONTACT_MAILTO} className="text-ink-2 transition-colors hover:text-accent">
                Request early access
              </a>
            </li>
          </ul>
        </div>
      </div>

      <div className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-5 py-5 text-[12px] text-muted lg:px-8">
          <p>© 2026 Kestrel Company Brain. All rights reserved.</p>
          <p>Built as a static site — no tracking scripts.</p>
        </div>
      </div>
    </footer>
  )
}
