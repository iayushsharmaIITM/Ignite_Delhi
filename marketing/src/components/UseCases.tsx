import { BookOpen, SearchCheck, ClipboardCheck } from "lucide-react"

const CASES = [
  {
    icon: BookOpen,
    title: "Understand internal documentation",
    example:
      "Ask what a policy actually says instead of re-reading a 40-page handbook — the answer quotes the section that matters.",
  },
  {
    icon: SearchCheck,
    title: "Find context across uploaded materials",
    example:
      "One question can pull from the contract, the incident ticket and the meeting notes at once, with each claim pointed at its document.",
  },
  {
    icon: ClipboardCheck,
    title: "Review information with source references",
    example:
      "Check whether dates, owners or commitments are consistent across files — and see exactly where they disagree.",
  },
]

export function UseCases() {
  return (
    <section aria-labelledby="usecases-heading" className="border-t border-line">
      <div className="mx-auto max-w-6xl px-5 py-20 lg:px-8 lg:py-28">
        <div className="reveal max-w-[58ch]">
          <p className="text-[12px] font-semibold uppercase tracking-[0.18em] text-accent">
            Use cases
          </p>
          <h2
            id="usecases-heading"
            className="mt-3 text-balance text-[30px] font-semibold tracking-[-0.015em] text-ink sm:text-[38px]"
          >
            Where teams reach for Kestrel
          </h2>
          <p className="mt-4 text-[15.5px] leading-relaxed text-muted">
            Illustrative examples drawn from the product's own demo corpus —
            your mileage depends on what you upload.
          </p>
        </div>

        <ul className="mt-12 grid gap-5 md:grid-cols-3">
          {CASES.map((c, i) => (
            <li
              key={c.title}
              className="reveal rounded-[14px] border border-line bg-panel p-6"
              style={{ transitionDelay: `${i * 60}ms` }}
            >
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-accent-dim text-accent">
                <c.icon className="h-5 w-5" aria-hidden />
              </span>
              <h3 className="mt-4 text-[16px] font-semibold text-ink">{c.title}</h3>
              <p className="mt-2 text-[13.5px] leading-relaxed text-muted">{c.example}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
