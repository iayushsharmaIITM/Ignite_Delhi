import { useEffect, useState } from "react"
import { Menu, X } from "lucide-react"
import { Logo } from "@/components/Logo"
import { CONTACT_MAILTO } from "@/contact"
import { cn } from "@/lib/cn"

const LINKS = [
  { href: "#product", label: "Product" },
  { href: "#how-it-works", label: "How it works" },
  { href: "#faq", label: "FAQ" },
]

export function Nav() {
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  // Close the mobile menu on Escape, and lock scroll while it is open.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false)
    document.addEventListener("keydown", onKey)
    document.body.style.overflow = "hidden"
    return () => {
      document.removeEventListener("keydown", onKey)
      document.body.style.overflow = ""
    }
  }, [open])

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-50 transition-colors duration-300",
        scrolled ? "border-b border-line bg-bg/85 backdrop-blur-md" : "bg-transparent",
      )}
    >
      <div className="mx-auto flex h-[68px] max-w-6xl items-center gap-6 px-5 lg:px-8">
        <a href="#top" aria-label="Kestrel — back to top" className="rounded-lg">
          <Logo />
        </a>

        <nav aria-label="Primary" className="ml-4 hidden items-center gap-1 lg:flex">
          {LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="rounded-lg px-3 py-2 text-[14px] text-muted transition-colors hover:text-ink"
            >
              {l.label}
            </a>
          ))}
        </nav>

        <div className="ml-auto hidden items-center gap-3 lg:flex">
          <a
            href={CONTACT_MAILTO}
            className="rounded-full bg-accent px-4 py-2 text-[13.5px] font-semibold text-accent-ink shadow-[0_0_20px_rgba(232,134,59,0.25)] transition-[transform,box-shadow] hover:-translate-y-px hover:shadow-[0_0_28px_rgba(232,134,59,0.4)]"
          >
            Request early access
          </a>
        </div>

        <button
          type="button"
          className="ml-auto inline-flex h-10 w-10 items-center justify-center rounded-lg border border-line-2 text-ink lg:hidden"
          aria-expanded={open}
          aria-controls="mobile-menu"
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen((o) => !o)}
        >
          {open ? <X className="h-5 w-5" aria-hidden /> : <Menu className="h-5 w-5" aria-hidden />}
        </button>
      </div>

      {open && (
        <div
          id="mobile-menu"
          className="border-t border-line bg-bg-2 px-5 pb-6 pt-3 lg:hidden"
        >
          <nav aria-label="Mobile" className="flex flex-col">
            {LINKS.map((l) => (
              <a
                key={l.href}
                href={l.href}
                onClick={() => setOpen(false)}
                className="rounded-lg px-2 py-3 text-[15px] text-ink-2 hover:bg-panel"
              >
                {l.label}
              </a>
            ))}
            <a
              href={CONTACT_MAILTO}
              className="mt-3 rounded-full bg-accent px-4 py-3 text-center text-[14.5px] font-semibold text-accent-ink"
            >
              Request early access
            </a>
          </nav>
        </div>
      )}
    </header>
  )
}
