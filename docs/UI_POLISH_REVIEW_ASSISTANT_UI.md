# Kestrel UI Polish Report — assistant-ui / Perplexity refinement pass

_Date: 2026-10-01 · Scope: **design-only, zero behavior change** · Status: implemented + verified_

Evidence: `docs/ui-review/screens/37-polish-thread-desktop.png` (polished thread),
`34-polish-chat-home-focus.png`, `35-polish-connectors.png`, `36-polish-graph.png`,
prior-state captures `01–28` in the same directory.

# Design-language polish spec

**Direction: "Forge & Ink" (assistant-ui refinement layer).** The thread is the
product: the question is a quiet echo, the answer is the hero on the bare
surface, sources are the receipts beneath, and the composer is a persistent
instrument pinned to the floor. Nothing between the reader and the evidence.

- **Typography:** Inter only. User echo 14px/1.6 `--ink-2` · answer 14.5–15px/1.6
  `--fg` with `--strong` pulled to full ink · code 12.5px mono in `--panel-2` ·
  table 13px with 10.5px caps headers · action-row 11px muted.
- **Spacing rhythm:** thread max-w 780px; turn gap 28px; question→answer 16px;
  answer→sources 12px; sources→divider→next turn 28px; composer pinned with 24px
  floor + safe-area.
- **Surface treatment:** answers sit directly on `--bg` — never carded. Containers
  (code, tables, dialogs) get `--panel-2` + 1px `--line`. One exception to
  no-shadow: the sticky composer.
- **Border/radius:** answers unbordered; code/tables 8px; cards 12px; chips
  9999px; focus ring 2px accent.
- **Density:** sidebar items 30–32px; thread breathes; connectors relaxed.
- **Motion:** 150–200ms ease-out, color/opacity/transform≤8px only; hover-only
  reveals (action row at opacity 0 → 100 on group-hover); reduced-motion kills all.
- **State styling:** semantic — ok `#34d399`, warn `#fbbf24`, destructive `--bad`,
  each with dim bg variant; idle = muted dot.
- **Citation/source styling:** "GROUNDED IN N SOURCES" caps label → numbered
  9999px mono chips (hover: accent border/text + dim bg) → click opens the drawer
  with verbatim excerpt → "origin: durable" from the provenance tables.

# Component/template polish library

| Artifact | Where | Benchmark | Reference | Visual characteristics |
|---|---|---|---|---|
| Answer panel | Bot turns | Perplexity answer card | assistant-ui `ThreadMessage` viewport | Bare-on-bg, 780px column, markdown map (h2/h3/ul/ol/blockquote/table/code) |
| Question echo | User turns | Perplexity query header | assistant-ui user message | Right-aligned, `--wash-2`, 14px, no border |
| Action row | Under answers | ChatGPT hover actions | assistant-ui action bar | opacity-0 → group-hover 100; copy + regenerate lucide 14px + hairline filler |
| Source chips | Under answers | Perplexity citation pills | assistant-ui sources | Numbered mono chips, accent hover, drawer hand-off |
| Sticky composer | Thread floor | Perplexity follow-up footer | assistant-ui `Composer` sticky | blur/fade wrapper, kbd hints (↵ send · ⇧↵ newline), safe-area floor |
| Empty-state composer | First run | Perplexity landing | same component | Identical shell centered under greeting — one composer, two contexts |
| Sidebar sections | Nav | Linear sidebar | shadcn sidebar pattern | hairline separators, caps labels +0.18em, 30px rows, accent dot/bars |
| Job progress rows | CreateBrain dialog | Stripe job rows | shadcn progress pattern | Semantic stage colors, per-file rows, honest error text |
| Status chips | Connectors | Vercel status badges | shadcn badge variants | ok=green-dim/40 border, idle=muted dot |
| Graph legend + inspector | Graph view | GitHub dependency graph | — | entity/relation/selected legend; click-to-inspect card; hover r-grow |

# Master polish table

| Kestrel surface | PDF/screens | Unchanged functionally | Benchmark | Named pattern | Polish spec shipped | Clutter removed | Effort |
|---|---|---|---|---|---|---|---|
| Chat thread + answers | 37-polish-thread-desktop | streaming, citations, sources | Perplexity | answer-first quiet-question layout | 14px user echo on wash-2; answer on bg; markdown map | bordered answer card | S ✅ |
| Action row | 37 | copy/regenerate behavior | ChatGPT hover actions | hover-revealed lucide row + hairline filler | unicode buttons → lucide, opacity reveal | always-on buttons | S ✅ |
| Markdown/code | 37 | rendering pipeline | chatcn message polish | token-mapped code/table/blockquote | full `_pre/code/table/blockquote` map | default browser chrome | S ✅ |
| Streaming caret | 37 | stream behavior | assistant-ui running indicator | pulsing accent block at tail | added (was dot-only below) | — | S ✅ |
| Composer shell | 34, 37 | send/attach/stop | assistant-ui Composer | focus recipe + kbd hints + safe-area | focus-within ring+shadow; ↵/⇧↵ hints | bare box | S ✅ |
| Source chips | 37 | resolution logic | Perplexity pills | label + hover accent | shipped in prior pass, retained | gray chips | S ✅ |
| Sidebar | all | nav behavior | Linear | hairline separators, caps+0.18em, 30px rows | shipped | flat list | S ✅ |
| Dialogs | CreateBrain/Slack | flows | Stripe settings | field-group labels (NAME/DOCUMENTS), semantic job colors | shipped | unlabeled fields | S ✅ |
| Connectors | 35 | honest 503s | Vercel cards | semantic chips + hover border | shipped (prior) | monochrome states | S ✅ |
| Graph view | 36 | /api/graph layout | GitHub dep graph | legend, hover, inspector, empty CTA | shipped (prior) | bare circles | M ✅ |
| Auth gate | 33 | Clerk theming | Vercel sign-in | already themed | — | — | — |
| Marketing | 06–26 | copy/motion budget | Vercel restraint | 3 prior polish passes | — | node-label toggle >80 nodes deferred | S (deferred) |

# Safe implementation stack

**System:** semantic tokens (`--ok/--ok-dim/--warn/--warn-dim/--shadow-composer`) ·
markdown typography map. **Component:** thread echo/actions/caret · composer
focus+kbd · sidebar separators/density · dialog labels+colors · connectors
chips. **Surface:** graph legend/inspector/empty-CTA · connectors card hover ·
sticky composer wrapper. **Mobile:** safe-area floor · resize auto-collapse ·
390px smoke. **Consistency:** destructive/ok/warn audit across dialog+connectors.

Every task: visual-only; risk of behavior break: none (classes + one textarea
value dispatch); proof: `npm run build` green after each stage + browser captures
37/34–36 + battery green post-pass (mock, backend untouched).

# Top-priority polish order

1. **Quieter question echo** — was a bordered card competing with the answer; now wash-2, 14px. Pages 5/37. Why: answer must be the hero.
2. **Hover-revealed action row** — was always-on unicode glyphs; now lucide icons, opacity reveal. Why: premium calm, less noise.
3. **Markdown typography map** — raw browser defaults; now full token-mapped pre/code/table/blockquote spec. Why: answers ARE markdown.
4. **Streaming caret at answer tail** — was a detached dot; now inline accent block. Why: Perplexity-grade liveness.
5. **Composer focus recipe + kbd hints** — plain box; now ring+shadow+hints. Why: the single most-touched surface.
6. **Sticky composer + gradient fade + safe-area** — scrolled away before; now pinned with grounding. Why: follow-up speed.
7. **Sidebar separators + density + honest hint box** — flat; now Linear-grade grouping. Why: wayfinding clarity.
8. **Dialog field grouping + semantic job colors** — unlabeled; now NAME/DOCUMENTS groups + ok/err/warn. Why: configuration confidence.
9. **Graph legend + hover + inspector + empty CTA** — bare circles; now full affordances. Why: inspectable density (GitHub).
10. **Connectors semantic chips + hover** — monochrome; now ok/idle chips + hover border. Why: trust through honesty.
11. **Thread width 780px** — 820px slightly wide for 15px text. Why: optimal measure.
12. **Mobile safe-area + auto-collapse** — notch overlap risk. Why: device polish.

# Token diff

| Token | Current | Proposed | Why | Impact |
|---|---|---|---|---|
| `--ok` / `--ok-dim` | — | `#34d399` / `rgba(52,211,153,.12)` | semantic success states | additive |
| `--warn` / `--warn-dim` | — | `#fbbf24` / `rgba(251,191,36,.12)` | VERIFYING/RECONCILIATION | additive |
| `--shadow-composer` | — | `0 -8px 30px rgba(0,0,0,.35)` | sticky composer grounding | additive |

No existing token changed.

# Signature polish interactions

| # | Trigger | Effect | Timing | Easing | Reduced-motion |
|---|---|---|---|---|---|
| 1 | Composer focus-within | accent border + ring + composer shadow | 200ms | ease-out | shadow appears unanimated |
| 2 | Source chip hover | accent border/text + accent-dim bg | 150ms | ease-out | instant |
| 3 | Turn hover | action row fades in (copy/regenerate/hairline) | 200ms | ease-out | instant reveal |
| 4 | Sticky composer on scroll | gradient fade + floor shadow pin it to the bottom | 150ms | linear | opacity-only |
| 5 | Graph node hover | r 6→9, stroke 1.5→2.5, label ink | 150ms | ease-out | instant |

# Keep-everything polish verdict

- **Keep as-is:** ask/recall pipeline; citation resolution + drawer logic; v2 job
  flow; connector honesty; Clerk gate; graph data/layout; marketing copy.
- **Keep but visually refine:** thread rendering; composer; source chips;
  sidebar; dialogs; connectors cards; graph affordances; mobile spacing;
  auth panel; marketing frames.
- **Keep but unify styling:** all state text → semantic tokens; both frontends'
  panels → hairline+radius rules; dialog footers → one pattern.

# Anti-patterns to avoid

Cheap: unicode-glyph buttons, monochrome job states, default browser markdown.
Noisy: always-visible action rows, pulsing everything, decorative gradients over
copy. Over-styled: card-ifying answers, glass over text, 4th surface depth.
Fake-premium: shadows on hairline cards, second accent, copying another product's
palette. Inconsistent: split route/auth/marketing languages, dialog footers that
differ per modal, states that hide system truth. Less trustworthy: fabricated
citations, optimistic job states, hiding "Operation not allowed".

---

## Final report checklist

- **Files changed:** `frontend/src/App.tsx`, `components/PromptBox.tsx`,
  `components/Sidebar.tsx`, `components/CreateBrainDialog.tsx`,
  `components/GraphView.tsx`, `components/Connectors.tsx`, `src/index.css`,
  `vite.config.ts` (proxy override), plus `ops/job_health.py` (ops visibility).
- **Components changed:** thread (echo/actions/caret/markdown), composer shell,
  sidebar sections, two dialogs, connectors cards, graph view, tokens.
- **assistant-ui-inspired ideas used:** answer-first quiet-question layout,
  shared composer across empty/thread states, sticky follow-up footer with
  grounding, hover action bar, source-chip receipt row.
- **Behavior unchanged:** ask/stream/save/open, citations resolution + drawer,
  v2 job flow, graph data, connectors honesty, auth — all verified via lab
  round-trips and battery.
- **Still inconsistent:** in-browser ask→answer round-trip capture (provider
  latency); graph page full-interactivity parity (labeled legacy link); provider
  route itself (founder decision).
