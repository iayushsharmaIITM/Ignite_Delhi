# Kestrel UI Review Request — for external model review (Claude)

**Attach together:** `UI_REVIEW_PACKAGE.pdf` (37 pages: cover, theme reference,
28 captioned screenshots in 5 groups, review-ask, reviewer context) + this file.

You are a senior product designer + design-engineer reviewing the **entire
Kestrel product UI**. The PDF is the evidence: 28 current-state captures of the
React app and the marketing site, grouped and captioned. Treat them as truth.

## The product
Kestrel is a company-knowledge workspace (dark, orange-accent, citations-first).
Stack: FastAPI + Cognee graph + Postgres + Clerk; React 19 + Tailwind v4 +
shadcn/ui frontend (vendored in `frontend/src/components/ui/`); a static
marketing site in `marketing/`. Current stage: private-beta tooling.

## The theme (the "ZCode-style" reference we committed to)
Dark charcoal surfaces, ONE warm orange accent, ivory text:

| Token | Dark value |
|---|---|
| bg / bg-2 / panel / panel-2 / panel-3 | `#1a1a1a` / `#161616` / `#212121` / `#2b2b2b` / `#333` |
| ink / ink-2 / muted | `#f2f0ec` / `#d6d2ca` / `#a8a49d` |
| accent / hover / dim / on-accent | `#E8873A` / `#F49D54` / `rgba(232,134,59,.12)` / `#1a1206` |
| lines | `#2e2e2e` / `#3a3a3a` |
| radius | 12px cards, 9999px pills; focus = 2px orange ring |
| type | Inter — titles 22–58px semibold, body 13.5–16.5px, labels 9.5–12px caps |

Rules: one accent only; dark-first; honest empty/disabled states with reasons;
AA contrast; reduced-motion; no decorative gradients over copy; no new frameworks.

## Screenshot inventory (44-page PDF)
- **App core (01–05)** — Slack "Configure access" dialog states, Connectors
  cards, chat home with attachment chips.
- **Marketing (06–19, 23–26)** — hero evolution, product demo, how-it-works,
  capabilities grid, tablet/mobile, menu, FAQ, OG card.
- **Legacy HTML shell (29–33) — the KEEP vs SWAP surface**: the full-featured
  HTML app served on :8000 (chat home with brain-grouped chats, Brains page,
  Upload page, Graph page) plus the LIVE :8000 Clerk auth gate.
- **Appendix (20–22)** — debug captures, context only.
- **App graph view (27–28)** — the NEW React graph (mobile + desktop), 93 nodes.

## THE CORE QUESTION — keep vs swap vs deprecate

Kestrel has TWO frontends. The legacy HTML shell is full-featured; the React
app is the design-forward primary but not yet at full parity. For **every
legacy surface and pattern**, classify:

- **KEEP** — genuinely better in the legacy shell; must be ported to React
  (name the pattern and where it goes in React).
- **SWAP** — React already does it better; the legacy shell should adopt
  React's design.
- **DEPRECATE** — should die entirely when parity lands.

Deliver: (a) the classification table per surface, (b) a ported-to-React
backlog ranked by impact-per-effort, (c) a "legacy retirement checklist" — the
exact parity conditions before the legacy shell is removed.

Surfaces to classify (at minimum): chat shell layout, brain-grouped chat
grouping, the composer (brain selector + attachments + suggestions), the work
log, brains management page, upload page, graph page, auth gate, empty states,
error rendering, keyboard behaviors.

## What to return (be blunt and specific)
1. **Per-screen verdicts** — hierarchy, composition, spacing, what's off.
2. **A concrete app-shell type + spacing scale** grounded in the tokens above.
3. **Top-10 component upgrades** (prompt box, thread, sidebar, dialogs, graph,
   connectors, empty states) — each with exact Tailwind/shadcn specs (classes,
   sizes, radii, states) and an impact-per-effort rank.
4. **Consistency audit** — where app and marketing diverge from the theme.
5. **Accessibility** — anything below AA on the dark theme, with fixes.
6. **Reference designs** — for the top upgrades, describe the target so precisely
   that an engineer can implement without asking questions.

Do not propose: new frameworks, light-first redesign, extra accent colors,
glassmorphism over copy, or anything that weakens honest states.

## Known constraints for your recommendations
- The app's empty/disabled states are REAL (Slack/Gmail/Drive not configured
  yet; connectors show 503-derived states). Do not suggest fake data.
- Generation routes are currently rate-limited — the empty answer in some
  captures is a provider limitation, not missing UI.
- Graph view is intentionally simple (circle layout); the legacy page remains
  linked for deep interactivity until parity is proven.
