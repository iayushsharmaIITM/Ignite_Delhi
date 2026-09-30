import { ChevronDown } from "lucide-react"
import { CONTACT_MAILTO } from "@/contact"

const QA = [
  {
    q: "What is a brain?",
    a: "A brain is a named collection of documents — one per client, product or team. You upload files into it, and questions against that brain are answered only from its contents. You can keep several brains and switch between them.",
  },
  {
    q: "What documents are supported?",
    a: "PDF (including scanned PDFs, which are read through an OCR model), Microsoft Word (.docx), plain text, Markdown, CSV, JSON, and common source-code files. Images are accepted as attachments to a question.",
  },
  {
    q: "How do citations work?",
    a: "Answers come back with numbered references. Each reference names the uploaded document it came from, and opening it shows the exact passage Kestrel used. If the documents don't contain an answer, Kestrel tells you rather than inventing one.",
  },
  {
    q: "How do I create an account?",
    a: "Kestrel is in active development and access is currently invite-based. Email us and we'll set you up with a workspace in the next beta round.",
    cta: true,
  },
  {
    q: "Are integrations available?",
    a: "Slack and email connectors are in development and labeled Coming soon — they are not usable yet. The core product (brains, uploads, cited Q&A, chat history and the knowledge-graph view) works today.",
  },
]

export function Faq() {
  return (
    <section id="faq" aria-labelledby="faq-heading" className="border-t border-line bg-bg-2">
      <div className="mx-auto max-w-3xl px-5 py-20 lg:px-8 lg:py-28">
        <div className="reveal text-center">
          <p className="text-[12px] font-semibold uppercase tracking-[0.18em] text-accent">FAQ</p>
          <h2
            id="faq-heading"
            className="mt-3 text-balance text-[30px] font-semibold tracking-[-0.015em] text-ink sm:text-[38px]"
          >
            Straight answers
          </h2>
        </div>

        <div className="reveal mt-10 flex flex-col gap-3">
          {QA.map((item) => (
            <details
              key={item.q}
              className="group rounded-[14px] border border-line bg-panel transition-colors open:border-line-2"
            >
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 rounded-[14px] px-5 py-4 text-[15px] font-semibold text-ink [&::-webkit-details-marker]:hidden">
                {item.q}
                <ChevronDown
                  aria-hidden
                  className="h-4.5 w-4.5 flex-none text-muted transition-transform duration-200 group-open:rotate-180 motion-reduce:transition-none"
                />
              </summary>
              <div className="px-5 pb-5">
                <p className="text-[14px] leading-relaxed text-muted">{item.a}</p>
                {item.cta && (
                  <a
                    href={CONTACT_MAILTO}
                    className="mt-3 inline-block rounded-full border border-line-2 px-4 py-2 text-[13px] font-semibold text-accent transition-colors hover:border-accent"
                  >
                    Request early access
                  </a>
                )}
              </div>
            </details>
          ))}
        </div>
      </div>
    </section>
  )
}
