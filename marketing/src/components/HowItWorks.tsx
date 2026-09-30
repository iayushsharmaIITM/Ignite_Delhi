import { FolderPlus, MessagesSquare, FileUp } from "lucide-react"

const STEPS = [
  {
    n: "01",
    icon: FolderPlus,
    title: "Create a brain",
    body: "A brain is a collection for one subject — a client, a product, a team. Keep as many as you need; each one answers only from its own documents.",
  },
  {
    n: "02",
    icon: FileUp,
    title: "Add your documents",
    body: "Upload PDFs (including scanned ones — Kestrel reads them with OCR), Word documents, Markdown, CSV, JSON and common code files. Files are re-ingested as you add them.",
  },
  {
    n: "03",
    icon: MessagesSquare,
    title: "Ask questions, inspect the sources",
    body: "Ask in plain language. Every answer streams with numbered citations — open one to read the exact passage that grounded the claim.",
  },
]

export function HowItWorks() {
  return (
    <section id="how-it-works" aria-labelledby="hiw-heading" className="border-t border-line">
      <div className="mx-auto max-w-6xl px-5 py-20 lg:px-8 lg:py-28">
        <div className="reveal max-w-[58ch]">
          <p className="text-[12px] font-semibold uppercase tracking-[0.18em] text-accent">
            How it works
          </p>
          <h2
            id="hiw-heading"
            className="mt-3 text-balance text-[30px] font-semibold tracking-[-0.015em] text-ink sm:text-[38px]"
          >
            Three steps, no migration project
          </h2>
        </div>

        <ol className="mt-12 grid gap-5 md:grid-cols-3">
          {STEPS.map((s, i) => (
            <li
              key={s.n}
              className="reveal relative rounded-[14px] border border-line bg-panel p-6"
              style={{ transitionDelay: `${i * 70}ms` }}
            >
              <div className="flex items-center justify-between">
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-accent-dim text-accent">
                  <s.icon className="h-5 w-5" aria-hidden />
                </span>
                <span aria-hidden className="font-mono text-[12px] text-muted">
                  {s.n}
                </span>
              </div>
              <h3 className="mt-5 text-[17px] font-semibold text-ink">{s.title}</h3>
              <p className="mt-2.5 text-[14px] leading-relaxed text-muted">{s.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}
