import {
  FolderLock,
  Quote,
  FileSearch,
  MessagesSquare,
  Waypoints,
  ScanText,
  Cable,
} from "lucide-react"

const FEATURES = [
  {
    icon: FolderLock,
    title: "Knowledge organized into brains",
    body: "Group documents by client, product or team. A brain answers only from what you put in it — no cross-contamination between collections.",
  },
  {
    icon: Quote,
    title: "Answers grounded in your sources",
    body: "Kestrel retrieves from your documents before answering, and says so when the answer isn't in them. No answer appears from thin air.",
  },
  {
    icon: FileSearch,
    title: "Citations you can open",
    body: "Numbered references on every answer open the source document and the exact excerpt behind the claim.",
  },
  {
    icon: MessagesSquare,
    title: "Conversations, not one-offs",
    body: "Threads keep their context, chats are saved per brain, and you can go back to any earlier question.",
  },
  {
    icon: Waypoints,
    title: "A graph of your knowledge",
    body: "Explore how documents, people and commitments connect — Kestrel builds a knowledge graph as it ingests.",
  },
  {
    icon: ScanText,
    title: "Scanned PDFs included",
    body: "Documents without a text layer are read through an OCR model, so contracts and faxes from the archive still answer questions.",
  },
]

export function Features() {
  return (
    <section aria-labelledby="features-heading" className="border-t border-line bg-bg-2">
      <div className="mx-auto max-w-6xl px-5 py-20 lg:px-8 lg:py-28">
        <div className="reveal max-w-[58ch]">
          <p className="text-[12px] font-semibold uppercase tracking-[0.18em] text-accent">
            Capabilities
          </p>
          <h2
            id="features-heading"
            className="mt-3 text-balance text-[30px] font-semibold tracking-[-0.015em] text-ink sm:text-[38px]"
          >
            Built and working today
          </h2>
          <p className="mt-4 text-[15.5px] leading-relaxed text-muted">
            Everything below is implemented in the current product build — this
            list is the feature set, not a roadmap.
          </p>
        </div>

        <ul className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => (
            <li
              key={f.title}
              className="reveal rounded-[14px] border border-line bg-panel p-6"
              style={{ transitionDelay: `${(i % 3) * 60}ms` }}
            >
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-accent-dim text-accent">
                <f.icon className="h-5 w-5" aria-hidden />
              </span>
              <h3 className="mt-4 text-[16px] font-semibold text-ink">{f.title}</h3>
              <p className="mt-2 text-[13.5px] leading-relaxed text-muted">{f.body}</p>
            </li>
          ))}
        </ul>

        {/* Planned, clearly labeled */}
        <div className="reveal mt-6 flex flex-wrap items-center gap-3 rounded-[14px] border border-dashed border-line-2 px-5 py-4">
          <span className="grid h-9 w-9 flex-none place-items-center rounded-xl bg-panel text-muted">
            <Cable className="h-4.5 w-4.5" aria-hidden />
          </span>
          <div className="min-w-0">
            <p className="text-[14px] font-semibold text-ink-2">
              Slack and email connectors
              <span className="ml-2 rounded-full border border-line-2 px-2 py-0.5 align-middle text-[10.5px] font-bold uppercase tracking-wide text-muted">
                Coming soon
              </span>
            </p>
            <p className="text-[13px] text-muted">
              Pull conversations into a brain and post answers back — in
              development, not yet available.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
