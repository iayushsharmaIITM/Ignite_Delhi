# Kestrel UI Polish Review — design-only refinement layer

_Date: 2026-10-01 · Evidence: `docs/ui-review/UI_REVIEW_PACKAGE.pdf` (33 captures)
+ live lab screens · Scope: **visual/interaction polish only — zero behavior change**_

Evidence tags: **OBSERVED** (visible in captures) · **RECALLED** (known benchmark
pattern) · **PROPOSED** (our recommendation). Nothing below changes flows,
routes, data, or honesty of states.

---

# Design-language polish spec

**Direction name: "Forge & Ink"** — a precision-instrument finish: dark
charcoal surfaces machined flat, one warm accent used like a marker on
important things only, ivory type set with restraint, hairlines instead of
shadows, and motion that never exceeds 200ms.

| Rule | Spec |
|---|---|
| Philosophy | A calm instrument for reading evidence. Everything else gets out of the way. |
| Typography | Inter. Thread answers 14.5–15px/1.6. Titles 22px/–0.01em. Labels 9.5–11px, +0.1em tracking, uppercase, muted. Never set body copy above 16px in the shell. |
| Spacing rhythm | 4px base. Shell gutters 24px (desktop) / 16px (mobile). Stack rhythm inside cards: 8/12/16. Section separation: 24–40px. Composer↔thread gap: 0 (they're one surface). |
| Surface treatment | Three depths only: `--bg` (page) → `--panel` (card) → `--panel-2` (inset/input). No fourth depth. Elevation via 1px hairlines (`--line-2`), not shadows — except the composer, which may float. |
| Border/radius | 12px cards/dialogs, 9999px pills/chips, 8px inputs. Borders are 1px `--line-2`; interactive borders shift to `accent/40` on hover, full accent on focus-visible. |
| Shadow rules | Shadows reserved for: the sticky composer, open popovers/dialogs. One recipe: `0 8px 30px rgba(0,0,0,.35)`. Nothing else casts shadow. |
| Density | Chat thread: max-w 820px, turn gap 24px. Sidebar items 32px tall. Connectors cards: relaxed (16px padding). Tables/graph: compact. |
| Motion rules | 120–200ms, `ease-out` only. Animate: color, border-color, opacity, transform ≤ 8px. Never animate: width, font-size, layout. `prefers-reduced-motion`: all transitions to 0.01ms (already global). |
| State styling | Loading = pulse dot + human label. Disabled = 50% opacity + reason text. Empty = one sentence + one CTA. Error = ⚠ + server message verbatim. Success = single green check line. |
| Citation/source styling | Chips are the unit: 9999px, hairline border, mono 11px. Hover = accent border + dim bg. Selected source panel = drawer with `--panel` bg and verbatim excerpt in `--panel-2`. |

# Component/template polish library

| Artifact | Purpose / where | Reference | Exact visual characteristics |
|---|---|---|---|
| Answer panel | Bot turns in the thread | Perplexity answer card; assistant-ui `ThreadMessage` | Max-w 820px; no card box on desktop (answer sits directly on `--bg`); "Grounded in N sources" label 11px muted above chips; 8px gap answer→sources |
| Source chip | Citation refs under answers | Perplexity citation pills | 9999px, 1px `--line-2`, mono 11px, `--muted`; hover: `accent/40` border + `--accent` text + `--accent-dim` bg, 150ms ease-out |
| Source drawer | Right panel with verbatim excerpt | Linear inspect panel | 420px drawer, `--panel` bg, 16px padding, title 13.5px semibold, excerpt in `--panel-2` 13px/1.6, copy button top-right |
| Sticky composer | Prompt box in thread view | ChatGPT/Perplexity pinned composer | Sticky bottom, `--panel` bg at 92% opacity + backdrop-blur 8px, top hairline `--line`, gradient fade 24px above (bg→transparent) |
| Sidebar section | Wayfinding groups | Linear sidebar | Label 9.5px caps +0.1em `--muted/70`; items 32px, 8px radius; hover `--wash`; active: `--sidebar-accent` bg + accent 2px left bar |
| Settings/integrations modal | CreateBrain + Slack dialogs | Stripe settings modals | 440–460px, radius 12, `--panel` bg, header 15px semibold + 13px muted sub, footer action full-width semibold button |
| Integration card | Connectors cards | Vercel integration cards | 1px `--line` → hover `accent/40`; icon tile 40px `--accent-dim`; status badges semantic (see states) |
| Graph inspector | Node detail in graph view | GitHub hovercards | 14px card, title 13.5px, meta 11px muted, no border radius beyond 8px |
| Auth panel | :8000 Clerk gate | Vercel sign-in | Centered 360px, single brand mark, one focus ring visible, no extra chrome |
| Marketing frame | Product screenshots on marketing site | Linear product frames | 12px radius, 1px `--line-2`, 40px ambient top-glow behind, no drop shadow |

# Master polish table

| Kestrel surface | PDF page(s) / screens file | Stays unchanged | Benchmark | Named pattern | Polish spec | Clutter to remove | Effort |
|---|---|---|---|---|---|---|---|
| Chat thread + answers | p.5 · `05-app-chat-home…`, live lab | Flow, streaming, citations logic | Perplexity answer card; assistant-ui | Answer on `--bg` (no card), source label + chips, 15px/1.6 ivory | Raw "step" label (fixed), heavy card border around answers | M (done) |
| Prompt box | p.5 · live | Send/attach behavior | Superhuman/Linear input feel | Focus: accent ring + composer shadow recipe; ↵/⇧↵ hint right-aligned 11px muted | None — box is already clean | S (done) |
| Sticky composer behavior | thread view (live) | Same component, sticky placement | ChatGPT pinned composer | Sticky bottom + backdrop-blur 8px + 24px gradient fade + top hairline on scroll | A floating look with no surface change | M (done) |
| Source chips + drawer | pp. 5, 4 | Resolution logic | Perplexity chips; Linear inspect | Hover accent state; drawer title + copy affordance | Generic gray chips look | S (done) |
| Sidebar | pp. 28–29 · live | Sections, search, grouping | Linear sidebar | Section labels +0.1em caps; 32px items; hover wash; active accent left-bar; honest empty hint box | Flat list feel | S (done) |
| Empty states / first-run | pp. 5, 28, 34 | Truthful copy | Linear empty states, Vercel first-run | One sentence + one CTA button (e.g. graph empty → "Create a brain"); soft accent glow behind brand mark | Bare italic text with no action | S (done) |
| Dialogs (CreateBrain, Slack) | pp. 1–4 | Job flow, radio/switch logic | Stripe settings modal | Job-state semantic colors (ok/warn/err); footer buttons full-width semibold; per-file rows with stage dots | Plain text states | S (done) |
| Graph view | pp. 35–36 · live lab | /api/graph data, layout | GitHub dependency graph; Figma minimap | Node hover grow + label ink; edge opacity 0.25; legend line; empty state w/ CTA; honest >120 truncation note | Bare circle layout with no affordances | M (done) |
| Connectors page | pp. 3–4 · `03-app-connectors…` | Honest 503 states | Vercel integration cards | Card hover accent border; status chips semantic; icon tiles 40px dim tiles | Same gray for all states | S (done) |
| Auth gate (:8000) | p. 37 · `33-live-8000…` | Clerk theming | Vercel sign-in | Already themed; add single brand mark above card | Clerk's extra header | — (live-gated) |
| Marketing hero | pp. 6–14, 26 | Copy, fallback, motion budget | Vercel/Linear restraint | Already through 3 polish passes | Node-label clutter at ring edges (toggle labels off at >80 nodes) | S (deferred) |
| Marketing sections | pp. 10, 23–25 | Copy, grid | Stripe editorial rhythm | Reveal stagger is 60ms — align to 40ms; settled grid gap 20px ✓ | Mid-reveal captures show stagger slightly long | S (deferred) |
| Mobile | pp. 15–18, 27, 35 | Overlay sidebar, flows | ChatGPT mobile composer | Composer safe-area padding (env(safe-area-inset-bottom)) | None observed | S |

Legend: items marked "done" were implemented in this pass (see commit + after-screenshots); "deferred/— " are queued, visual-only.

# Safe implementation stack

**System polish**
1. `Semantic state tokens` — add `--ok/--ok-dim/--warn/--warn-dim` (mapped in @theme). Files: `frontend/src/index.css`. Visual-only. Risk: none. Proof: battery + build.
2. `Composer shadow recipe` — one `--shadow-composer` token. Same file. Visual-only. Proof: build.

**Component polish**
3. `PromptBox focus + hint` — focus ring + kbd hint + hover border. `PromptBox.tsx`. Visual-only. Proof: browser focus screenshot.
4. `Answer panel + source chips` — label/chips/hover per spec. `App.tsx`. Visual-only. Proof: ask on lab (harbor window permitting) or existing thread render.
5. `Sidebar active/hover` — accent left-bar + hover wash. `Sidebar.tsx`. Visual-only. Proof: screenshot.
6. `Dialog job-state colors` — semantic classes for job/file states. `CreateBrainDialog.tsx`. Visual-only. Proof: screenshot during a v2 run.
7. `Connectors semantic chips + card hover` — `Connectors.tsx`. Visual-only. Proof: screenshot.
8. `Graph affordances + empty CTA` — hover, legend, empty CTA. `GraphView.tsx` (+ optional `onCreate` prop from `App.tsx`). Visual-only. Proof: screenshot both states.

**Surface polish**
9. `Sticky composer + fade` — thread-view composer; scroll listener toggles fade/hairline. `App.tsx`. Visual-only. Risk: none (CSS/overlay). Proof: scrolled screenshot.
10. `Empty-chat brand glow` — soft radial behind brand mark. `App.tsx`. Visual-only. Proof: screenshot.

**Mobile polish**
11. `Composer safe-area` — `env(safe-area-inset-bottom)` padding. `App.tsx`. Visual-only. Proof: 390px screenshot.

**Consistency sweep**
12. `Semantic color audit` — grep destructive/warn/ok usages; align all state text to the new tokens. Proof: grep output + screenshots.

# Top-priority polish order

1. **Semantic state tokens** — currently job/dialog states are monochrome text (OBSERVED pp. 1–4); premium apps color-code outcomes. Visual-only: new tokens, no existing value changes.
2. **Sticky composer + gradient fade** (OBSERVED: composer scrolls away with content in long threads — p.5 live) — keeps the primary input one keystroke away. Behavior unchanged: same component, position only.
3. **Answer panel treatment** (OBSERVED: answers read slightly heavy inside default styling) — 15px/1.6 ivory, source label + accent-hover chips.
4. **PromptBox focus + kbd hint** (OBSERVED: focus state is a plain outline) — accent ring + shadow recipe + ↵ hint = instant "premium input" read.
5. **Sidebar active/hover** (OBSERVED: active chat indistinguishable on scan) — accent left-bar + hover wash.
6. **Connectors semantic chips + card hover** (OBSERVED: "OAuth ready" and "not configured" look identical-weight) — outcomes get colors.
7. **Graph affordances** (OBSERVED: 93 nodes but no hover/legend/CTA) — hover grow, legend, empty-state CTA.
8. **Dialog job-state colors** — same semantic mapping in CreateBrain progress.
9. **Empty-chat brand glow** — soft radial behind the mark; kills the "flat rotated square" starkness.
10. **Mobile composer safe-area** — notched-device spacing.
11. **Sidebar empty hint styling** — bordered hint box, keeps honest copy.
12. **Consistency sweep** — align every state text to semantic tokens.

# Token diff

| Token | Current | Proposed | Why | Impact |
|---|---|---|---|---|
| `--ok` | — | `#34d399` | Job success / connected states | New utility |
| `--ok-dim` | — | `rgba(52,211,153,.12)` | Success chip/tile bg | New utility |
| `--warn` | — | `#fbbf24` | VERIFYING/RECONCILIATION states | New utility |
| `--warn-dim` | — | `rgba(251,191,36,.12)` | Warn chip/tile bg | New utility |
| `--shadow-composer` | — | `0 -8px 30px rgba(0,0,0,.35)` | Sticky composer float | New utility |

No existing token values change. All additions are additive utilities.

# Signature polish interactions

| # | Trigger | Visible effect | Timing | Easing | Reduced-motion |
|---|---|---|---|---|---|
| 1 | Composer textarea focus | Border → accent/60 + composer shadow recipe appears | 200ms | ease-out | Shadow only, no transition |
| 2 | Source chip hover | Border/text → accent, bg → accent-dim | 150ms | ease-out | Instant state swap |
| 3 | Sidebar chat item hover | Dot → accent, title → ink, bg → wash | 120ms | ease-out | Instant |
| 4 | Thread scroll (composer sticky) | 24px gradient fade + top hairline fade in | 150ms | linear | None (opacity only) |
| 5 | Graph node hover | r 6→9, stroke-width 1.5→2.5, label → ink | 150ms | ease-out | Instant |

All five are color/opacity/transform-only; behavior identical.

# Keep-everything polish verdict

- **Keep as-is:** all flows; chat/logic; citations resolution; v2 job machinery;
  honest states' *copy*; Clerk gate function; marketing copy/structure;
  graph data/layout algorithm.
- **Keep but visually refine:** prompt box; thread/answers; source chips +
  drawer; sidebar; dialogs (CreateBrain, Slack); connectors cards; graph view;
  empty states; auth panel theming; marketing hero motion; mobile adaptations.
- **Keep but unify styling:** every state text → semantic tokens; both
  frontends' shared surfaces (sidebar/panels) → same hairline+radius rules;
  dialog footers → one button pattern.

# Anti-patterns to avoid

1. Glowing gradients behind reading surfaces (kills the "instrument" feel).
2. A second accent color for states — use dim/saturated pairs of the semantic
   greens/ambers, never blue/purple.
3. Card-ifying everything — the thread must stay on `--bg`; cards are for
   containers, not content.
4. Animated placeholders/shimmer loops in idle states — motion belongs to
   transitions, not resting UI.
5. Rounded-everything drift — inputs stay 8px; only cards/pills get 12/9999.
6. Icon-only buttons without aria-labels (regression risk during polish).
7. Drop shadows on hairline-bordered cards — pick one depth cue per element.
8. Prefixing states with emoji instead of semantic color (cheapens copy).
9. Matching benchmark products pixel-for-pixel on *their* dark values — the
   palette must stay in Kestrel's charcoal family.
10. Polishing the provider-failure states into invisibility — they must stay
    visible and honest.

---

## Implementation status (2026-10-01, same day)

All 12 stack items **implemented** (visual-only, commit `feat(polish)…`):
semantic tokens, PromptBox focus+kbd, source label/chips hover, sticky composer
fade + safe-area, sidebar active/hover, graph legend/hover/empty-CTA,
Connectors semantic chips + card hover, dialog job-state colors, brand glow,
consistency sweep. Build green. After-captures: screens/34–36. Top-12 order:
items 1–9 shipped; 10 (safe-area) shipped; 11 shipped; 12 shipped as part of
each. Remaining deferred: marketing hero node-label toggle at >80 nodes,
per-chunk citation offsets, any provider-dependent captures.
