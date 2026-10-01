# Prompt for Claude — "Multi-Billion-Dollar" UI/UX Benchmark & Remap

**Attach together with this prompt:**
1. `docs/ui-review/UI_REVIEW_PACKAGE.pdf` — 44 pages, 33 captioned screenshots
   (React app, dialogs, graph view, the legacy HTML shell, marketing site,
   mobile/tablet, theme reference page with swatches)
2. `docs/ui-review/REVIEW_REQUEST.md` — product context, token table,
   inventory, the KEEP vs SWAP vs DEPRECATE question

---

## THE PROMPT (copy everything below)

You are a design principal who has personally shipped and scaled the design
systems behind multi-billion-dollar products — the Linear command bar, Notion's
calm-document canvas, Stripe's dashboard density, Vercel's marketing restraint,
Superhuman's speed-feel, Arc's spatial navigation, Perplexity's answer-first
layout, Slack's wayfinding, GitHub's information density. You know these
systems down to the pixel: their spacing scales, their motion curves, their
empty states, their keyboard models, and — most importantly — **why each
decision made the product feel inevitable rather than decorated**.

You are now redesigning **Kestrel**, a company-knowledge workspace (chat with
a knowledge graph, cited answers, document brains), currently at private-beta
quality. The attached PDF is the complete visual evidence: 33 current-state
captures of both Kestrel frontends plus its design-token system. The attached
REVIEW_REQUEST.md contains the product context, the full token table, and the
two-frontends KEEP vs SWAP vs DEPRECATE question.

**Your mission: benchmark Kestrel against the best products on earth and
produce a mapped, implementable upgrade plan — no vibes, only named
references and exact specifications.**

### The benchmark map you must produce

For each of the 10 core surfaces below, deliver one row in a master table:

| Column | Required content |
|---|---|
| Kestrel surface | The exact screen/region from the PDF (cite page number) |
| Reference product | The multi-billion-dollar product whose pattern Kestrel should adopt — **named** (e.g. "Linear", not "a modern app") |
| Named pattern | The specific feature/pattern to copy — named precisely (e.g. "Linear's ⌘K command palette with two-level nesting", "Notion's hover-revealed block handles", "Stripe's 8px-grid table density") |
| Why this reference | One sentence on why it fits Kestrel's specific job-to-be-done |
| Exact spec | Font sizes, weights, spacing values, radii, colors (mapped onto Kestrel's existing tokens — #E8873A accent, #1a1a1a surfaces, ivory #f2f0ec), motion (duration + easing), and the shadcn/Tailwind classes to implement it |
| What to delete | What in the current screenshot gets removed to make room |
| Effort | S / M / L |

The 10 surfaces (page numbers refer to the PDF):

1. **Chat thread & answer rendering** (pp. 5, 10) — benchmark: the best
   answer-first AI products (Perplexity's citation chips, Claude/ChatGPT's
   streaming typography, Notion AI's inline actions)
2. **Prompt box / composer** (pp. 5, 28) — benchmark: Superhuman/Linear input
   feel, ChatGPT's attachment affordances, Perplexity's focus ring behavior
3. **Left sidebar & wayfinding** (pp. 28–29, 34) — benchmark: Linear's
   sidebar hierarchy and collapsible sections, Slack's unreads model,
   Notion's page-tree affordances
4. **Empty states & first-run** (pp. 28, 34) — benchmark: Linear's project
   empty states, Vercel's first-run clarity, Notion's template gallery
5. **Dialogs & configuration surfaces** (pp. 1–4 — Slack "Configure access"
   dialog) — benchmark: Stripe settings pages, Linear's settings modals,
   Vercel's project settings rhythm
6. **Knowledge graph view** (pp. 35–36) — benchmark: GitHub's dependency
   graph, Figma's canvas minimap, Linear's roadmap graph — for legibility at
   93+ nodes
7. **Connectors / integrations page** (pp. 3–4) — benchmark: Vercel's
   integrations marketplace cards, Slack's app directory states, Stripe's
   partner page trust markers
8. **Auth gate** (p. 37) — benchmark: Vercel/Linear/Notion sign-in screens —
   restraint, brand moment, focus discipline
9. **Marketing hero & sections** (pp. 7–19) — benchmark: Vercel/Linear
   marketing motion, Stripe's editorial restraint, Perplexity's product-truth
   screenshots
10. **Mobile adaptations** (pp. 16–18, 35) — benchmark: ChatGPT mobile's
    composer, Notion mobile's navigation collapse

### The design-language spec you must also deliver

Beyond the per-surface map, write the **target design language** for Kestrel
as if it were the next multi-billion-dollar product: a named direction (give
it a real name, not "modern"), a one-paragraph philosophy, and the concrete
system that expresses it — refined token adjustments (if any of Kestrel's
existing tokens should change values), elevation/shadow rules, motion rules
(durations, easings, what animates and what never does), density rules, and
the 5 signature interactions that would make Kestrel feel like a
billion-dollar product rather than a beta.

### Non-negotiable constraints

- Dark-first. One accent (#E8873A family). No second accent, no purple/blue
  gradients, no glassmorphism over copy.
- shadcn/ui + Tailwind v4 stay. Recommendations must be implementable with
  them (custom CSS allowed where needed).
- Honest states are a feature: "not configured", "no workspaces connected"
  must remain truthful — improve their *design*, not their honesty.
- The two-frontends reality: your KEEP/SWAP/DEPRECATE verdict per legacy
  surface (see REVIEW_REQUEST.md) must be integrated into the map.
- Accessibility: AA on dark, focus discipline, reduced-motion — reference how
  your benchmark products handle these.
- Every named reference must come with **where to study it** (the exact
  product area, docs page, or keyboard shortcut), so an engineer can go look.

### Output format (exactly these sections)

1. **Design-language spec** — named direction, philosophy, system rules
2. **The master benchmark table** — 10 surfaces × the 7 columns above
3. **The top-10 upgrade sequence** — ranked by impact-per-effort, each with
   before/after description, exact specs, and the page number it fixes
4. **Token diff** — current tokens vs adjusted tokens (a table, only what
   changes)
5. **Signature interactions** — the 5 moments that would make Kestrel feel
   inevitable
6. **KEEP/SWAP/DEPRECATE verdict** — per legacy surface (from REVIEW_REQUEST)
7. **Anti-patterns to avoid** — what would make Kestrel feel cheap, specific
   to what you saw in the PDF
8. **30/60/90 implementation order** — with effort sizes

Do not produce generic advice ("improve spacing", "use whitespace"). Every
sentence must be implementable on the attached evidence. If a screenshot
reveals something broken, say it plainly.

---

## How the founder uses this

1. Attach the PDF + REVIEW_REQUEST.md + this prompt to Claude in one message.
2. When the response returns, bring it back to ZCode — every "Exact spec" cell
   gets converted into real commits, verified the same way as everything else.
3. Reference sources the reviewer names (Linear/Notion/etc.) can be captured
   with browser screenshots on request, so each spec gets a pixel-truth
   comparison here at home.
