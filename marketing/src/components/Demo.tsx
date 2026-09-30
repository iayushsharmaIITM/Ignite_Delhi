import { Diamond, FileText, Folder, MessagesSquare, Waypoints } from "lucide-react"

const SOURCES = [
  {
    n: 1,
    name: "01_contract_MSA-2025-0114_bluepeak.md",
    quote: "§7.2 — Bluepeak uptime commitment and the service-credit schedule that follows any confirmed P1.",
  },
  {
    n: 2,
    name: "02_ticket_4412_p1_outage.md",
    quote: "P1 outage confirmed; SLA credit flagged for approval — status: pending.",
  },
  {
    n: 3,
    name: "03_meeting_2026-08-14_bluepeak_renewal.md",
    quote: "Renewal window discussed; actions carried into the Aug 28 QBR agenda.",
  },
]

/**
 * A faithful, hand-built mock of the app shell (sidebar + thread + source
 * panel) using the repo's own synthetic demo corpus. Deliberately not a
 * screenshot: it stays crisp at every DPI and carries real markup for
 * screen readers, with the simulation label spelled out below.
 */
export function Demo() {
  return (
    <section id="product" aria-labelledby="demo-heading" className="border-t border-line bg-bg-2">
      <div className="mx-auto max-w-6xl px-5 py-20 lg:px-8 lg:py-28">
        <div className="reveal mx-auto max-w-[62ch] text-center">
          <p className="text-[12px] font-semibold uppercase tracking-[0.18em] text-accent">
            Product
          </p>
          <h2
            id="demo-heading"
            className="mt-3 text-balance text-[30px] font-semibold tracking-[-0.015em] text-ink sm:text-[38px]"
          >
            Ask in plain language. Answer with receipts.
          </h2>
          <p className="mt-4 text-[15.5px] leading-relaxed text-muted">
            Every answer carries numbered citations. Open one and Kestrel shows
            the exact passage it drew from — in the document you uploaded.
          </p>
        </div>

        <div className="reveal mx-auto mt-12 max-w-[980px]">
          <div className="overflow-hidden rounded-[16px] border border-line-2 bg-bg shadow-[0_24px_80px_rgba(0,0,0,0.45)]">
            {/* window chrome */}
            <div className="flex items-center gap-2 border-b border-line bg-panel px-4 py-2.5">
              <span aria-hidden className="h-2.5 w-2.5 rounded-full bg-[#3a3a3a]" />
              <span aria-hidden className="h-2.5 w-2.5 rounded-full bg-[#3a3a3a]" />
              <span aria-hidden className="h-2.5 w-2.5 rounded-full bg-[#3a3a3a]" />
              <span className="ml-3 truncate text-[11.5px] text-muted">
                Kestrel workspace — company_brain
              </span>
            </div>

            <div className="grid md:grid-cols-[168px_minmax(0,1fr)] lg:grid-cols-[180px_minmax(0,1fr)_260px]">
              {/* sidebar */}
              <div className="hidden flex-col gap-1 border-r border-line bg-bg-2 p-3 md:flex" aria-hidden>
                <div className="mb-2 flex items-center gap-2 px-1.5">
                  <span className="grid h-6 w-6 place-items-center rounded-md bg-accent">
                    <Diamond className="h-3 w-3 text-[#1a1206]" fill="currentColor" />
                  </span>
                  <span className="text-[12.5px] font-semibold text-ink">Kestrel</span>
                </div>
                <p className="px-1.5 pb-1 text-[9.5px] font-bold uppercase tracking-[0.14em] text-muted">
                  Brains
                </p>
                {["company_brain", "hghi", "kestrel_full"].map((b, i) => (
                  <div
                    key={b}
                    className={`flex items-center gap-2 rounded-lg px-1.5 py-1.5 text-[12px] ${
                      i === 0 ? "bg-panel text-ink" : "text-muted"
                    }`}
                  >
                    <Folder className="h-3.5 w-3.5 opacity-70" />
                    <span className="truncate">{b}</span>
                  </div>
                ))}
                <p className="mt-3 px-1.5 pb-1 text-[9.5px] font-bold uppercase tracking-[0.14em] text-muted">
                  Views
                </p>
                <div className="flex items-center gap-2 rounded-lg px-1.5 py-1.5 text-[12px] text-muted">
                  <Waypoints className="h-3.5 w-3.5 opacity-70" /> Graph
                </div>
                <div className="flex items-center gap-2 rounded-lg px-1.5 py-1.5 text-[12px] text-muted">
                  <MessagesSquare className="h-3.5 w-3.5 opacity-70" /> Chats
                </div>
              </div>

              {/* thread */}
              <div className="flex min-h-[380px] flex-col gap-4 p-4 sm:p-6">
                <div className="flex justify-end">
                  <p className="max-w-[85%] rounded-2xl rounded-br-md border border-line bg-panel px-4 py-2.5 text-[13.5px] text-ink">
                    Why is the Bluepeak renewal at risk, and what have we
                    promised them?
                  </p>
                </div>
                <div className="max-w-[92%]">
                  <div className="text-[13.5px] leading-relaxed text-ink-2">
                    <p>
                      The renewal is at risk because August's P1 outage breached
                      the uptime commitment in the MSA, and the service credit
                      that policy triggers is still pending approval.
                      <sup>
                        <span className="citation-chip">1</span>
                      </sup>
                      <sup>
                        <span className="citation-chip">2</span>
                      </sup>{" "}
                      What you've promised: a scheduled service credit and a
                      remediation review at the next QBR.
                      <sup>
                        <span className="citation-chip">3</span>
                      </sup>
                    </p>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1.5" aria-label="Cited sources">
                    {SOURCES.map((s) => (
                      <span
                        key={s.n}
                        className="inline-flex items-center gap-1 rounded-full border border-line-2 px-2 py-0.5 font-mono text-[10.5px] text-muted"
                      >
                        {s.n}. {s.name.replace(/_bluepeak|\.md|0\d_/g, "")}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="mt-auto flex items-center gap-2 rounded-2xl border border-line bg-panel px-3.5 py-2.5" aria-hidden>
                  <span className="text-[12.5px] text-muted">
                    Ask across every document the company has written…
                  </span>
                  <span className="ml-auto grid h-7 w-7 place-items-center rounded-full bg-accent">
                    <Diamond className="h-2.5 w-2.5 text-[#1a1206]" fill="currentColor" />
                  </span>
                </div>
              </div>

              {/* sources panel */}
              <aside
                aria-label="Source references (example)"
                className="hidden border-l border-line bg-bg-2 p-3.5 lg:block"
              >
                <p className="pb-2 text-[10px] font-bold uppercase tracking-[0.14em] text-muted">
                  Sources
                </p>
                <ul className="flex flex-col gap-2.5">
                  {SOURCES.map((s) => (
                    <li key={s.n} className="rounded-xl border border-line bg-panel p-3">
                      <p className="flex items-start gap-1.5 text-[11px] font-medium text-ink">
                        <FileText className="mt-0.5 h-3 w-3 flex-none text-accent" />
                        <span className="break-all">{s.name}</span>
                      </p>
                      <p className="mt-1.5 border-l-2 border-accent/50 pl-2 text-[11px] leading-relaxed text-muted">
                        {s.quote}
                      </p>
                    </li>
                  ))}
                </ul>
              </aside>
            </div>
          </div>
          <p className="mt-4 text-center text-[12px] text-muted">
            Simulated walkthrough built from synthetic example documents — not a
            live product session.
          </p>
        </div>
      </div>
    </section>
  )
}
