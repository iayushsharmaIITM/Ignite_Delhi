# Kestrel Design System

The React frontend (`/frontend`) — tokens, components, and the rules that
keep it one product instead of a pile of one-off styles.

## Stack

| Layer      | Choice                                   | Why |
|------------|------------------------------------------|-----|
| Build      | Vite 8 + React 19 + TypeScript           | Fast HMR; `tsc -b` gate on every build |
| Styling    | Tailwind CSS v4 (`@tailwindcss/vite`)    | Tokens live in CSS variables, utilities compile from them |
| Components | shadcn/ui (Radix primitives, vendored in `src/components/ui/`) | Own the code; a11y for free (focus trap, roving tabindex, ARIA) |
| Markdown   | react-markdown + remark-gfm (lazy chunk) | ~150 kB stays out of the first paint |
| Toasts     | sonner                                   | Theme-aware, ARIA live region built in |

Dev: `cd frontend && npm run dev` (port 5173, `/api` + `/health` proxy to the
FastAPI server on :8000). Build: `npm run build` → `dist/`.

## Tokens (`src/index.css`)

CSS variables are the single source of truth. Tailwind's `@theme inline`
block maps them into utility classes (`bg-card`, `text-muted-foreground`, …),
so a theme switch is one `data-theme` attribute — no component changes.

| Token             | Dark (default)   | Light (`data-theme="light"`) | Used for |
|-------------------|------------------|------------------------------|----------|
| `--bg`            | `#1a1a1a`        | `#f7f5f1` warm paper         | App background |
| `--bg-2`          | `#161616`        | `#efece6`                    | Sidebar |
| `--panel`         | `#212121`        | `#ffffff`                    | Cards, dialogs, popovers |
| `--panel-2`       | `#2b2b2b`        | `#ece9e2`                    | Inputs, code blocks |
| `--fg`            | `#f2f0ec`        | `#241f18`                    | Primary text |
| `--muted`         | `#a8a49d`        | `#6d675e`                    | Secondary text |
| `--accent`        | `#e8873a`        | `#b45309` (darkened for AA)  | THE orange — one hue, never two |
| `--accent-ink`    | `#1a1206`        | `#ffffff`                    | Text on orange |
| `--line`/`--line-2` | hairlines      | hairlines                    | Borders |
| `--accent-dim`    | orange @ 12%     | orange @ 12%                 | Selected-state tint |

Rules:

- **One accent.** Orange marks interactive/selected. If something is orange
  and not interactive, it's wrong.
- **Radius:** 12px on cards/dialogs/inputs (`rounded-xl`, `--radius-card`),
  9999px on chips/pills/avatars. Nothing in between.
- **Contrast:** every text pair meets WCAG AA in BOTH themes (the light accent
  is deliberately darker than the brand orange for this).
- **Focus:** `:focus-visible` = 2px orange ring, everywhere, no exceptions.
- **Motion:** `prefers-reduced-motion` collapses transitions to 1ms.

## Layout

```
┌──────────┬─────────────────────────────────┐
│ Sidebar  │  main (chat | connectors)       │
│ 268px    │  content column, max-w 820px    │
│ collaps. │  prompt box pinned bottom       │
└──────────┴─────────────────────────────────┘
```

- Sidebar collapses to 0 with a floating expand button (PanelLeft) so there
  is always a way back. Under 768px it is a fixed overlay and auto-collapses
  after navigation.
- Empty state (greeting + chips) and thread share the same 820px column.
- Citations open a right-side panel (420px) — never a modal.

## Component inventory

**Vendored shadcn primitives** (`src/components/ui/`): button, input, badge,
dialog, dropdown-menu, popover, radio-group, switch, tooltip, command,
separator, scroll-area, skeleton, sheet, sonner.

**Product components** (`src/components/`):

- `Sidebar.tsx` — brains as folders, chat search, per-chat hover menu
  (rename/pin/two-step delete), tooltips on collapse.
- `PromptBox.tsx` — auto-growing textarea, Enter/Shift+Enter, drag-drop
  attachments with removable chips, streaming stop, live stage label,
  brain chip.
- `Connectors.tsx` — Slack/Google cards with honest state chips
  ("OAuth ready" vs "OAuth not configured"), connected-workspace list with
  mode badges, two-step disconnect.
- `SlackAccessDialog.tsx` — "Configure access": RadioGroup (Read and post
  = Recommended default / Read only), private-content Switch, Connect →
  `/api/connectors/slack/connect?mode=&private=`.
- `Markdown.tsx` — lazy-loaded GFM renderer.

**Shell** (`src/App.tsx`): streaming NDJSON reader (chunk / references /
stage events), per-message copy + regenerate, OAuth landing-pad toasts
(`/?connected=…`, `/?connect_error=…`), timezone params (`tz`, `local_time`,
additive — the server treats them as hints), theme bootstrap.

## Before / after

| # | Improvement            | Before (legacy `static/`)              | After (React UI) |
|---|------------------------|----------------------------------------|------------------|
| 1 | Tokens                 | 4 near-identical hex blocks per page   | One `:root` block; themes swap via `data-theme` |
| 2 | Sidebar                | Static link list                       | Collapsible, searchable, brain folders, hover menus, tooltips, reopen button |
| 3 | Prompt box             | Fixed-height input, `alert()` on attach| Auto-grow, file chips, stop, stage label, drag-drop |
| 4 | Answers                | Plain text, full-bleed                 | GFM markdown (lazy chunk), code/table styling, max-width column |
| 5 | Citations              | Inline text only                       | Numbered chips → right source panel with excerpt |
| 6 | Message actions        | None                                   | Copy + regenerate per answer |
| 7 | Auth screens           | Clerk default branding + duplicate header | Theme-matched variables, Clerk header hidden, single title |
| 8 | Connectors             | Hidden behind legacy page              | Connectors view + Configure access dialog wired to the real scope-picker flow |
| 9 | A11y                   | Unaudited                              | Landmarks, skip link, aria labels on every icon button, AA contrast both themes, visible orange focus ring, reduced-motion |
| 10| Responsive             | Desktop only                           | Sidebar overlays and auto-collapses < 768px; column fluid down to 360px |

## Rules for new UI code

1. No raw hex in components — use token utilities (`bg-card`, not `bg-[#212121]`).
2. Every icon-only control gets `aria-label`; every dialog gets a title + description.
3. New interactive element → must show a focus ring and have a hover AND a
   keyboard path.
4. Empty states say what to do next, never "No data".
5. Honest states: a button that cannot work yet is disabled WITH the reason
   ("Slack app not configured"), never silently dead.
6. API contracts stay additive — the React UI consumes the same routes as the
   legacy shell (`/api/ask`, `/api/extract`, `/api/connectors/*`), sends the
   same params, and adds only `tz`/`local_time`.
