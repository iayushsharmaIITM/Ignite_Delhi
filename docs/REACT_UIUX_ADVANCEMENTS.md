# Kestrel — React Desktop Dashboard: UI/UX System & Advancements

> **Status correction (2026-10-03, after `docs/FRONTEND_FIX_PLAN.md`).** This
> document was written while the port was verified only through the Vite dev
> server, and several claims below were true of that setup rather than of the
> product. The plan was executed (Phases A–E) and this file has been corrected
> where it mattered; the corrections are marked `[fixed]` inline. Two claims are
> worth knowing before reading: the React app is now what `python app.py` serves
> at `/` (it was not — `static/index.html` was), and the "pixel-diff parity
> gates" below were capture helpers, not gates. The authoritative record is
> `docs/FRONTEND_FIX_PLAN.md` §6 (execution status).

_A design-system deep dive for LLM review. Written 2026-10-03. Everything
described here is **built and verified** — file paths are given so every claim
can be cross-checked against the code. Review target: the `frontend/` React
application (React 19 + Vite + Tailwind v4), which **`[fixed]`** is served by
`app.py` at `/` under `KESTREL_UI=react` (the default), replacing the legacy
`static/index.html` dashboard as the product's frontend._

**Reviewer orientation.** This app went through an unusual port: instead of
re-styling a new frontend, the legacy HTML dashboard's *exact* stylesheets
were made load-bearing in React, and React re-renders the legacy DOM
selectors 1:1. That decision is the spine of the whole design system —
understand §2 first; everything else follows from it.

---

## 1. Platform state (what exists today)

| Layer | What's real |
|---|---|
| Web frontend | `frontend/` — React 19, Vite, Tailwind v4 (`@tailwindcss/vite`), shadcn-style primitives in `frontend/src/components/ui/`, sonner toasts, custom i18n (`lib/i18n.ts`, 6 languages), Clerk auth via CDN loader (`lib/clerk.ts`), self-hosted Inter (`@fontsource-variable/inter`). Served from the backend at `/` (`KESTREL_UI`, default `react`); `frontend/dist` is committed and CI rebuilds+diffs it |
| Design system | `frontend/src/design/deck.css` and `frontend/src/design/shell.css` — imported globally, they style the React DOM. **Corrected 2026-10-04:** this row read "Legacy stylesheets … `frontend/src/legacy/…` (= `static/shell.css` verbatim)". The directory was renamed to `design/` because `legacy/` read as dead code to every reviewer while being the product's whole visual language, and the `static/` files it was copied from are now deleted, so "verbatim" had no referent left. Their provenance is unchanged: deck.css is the old shell's stylesheet, shell.css is the old chat page's inline `<style>` |
| Backend | Same-origin `app.py` (FastAPI): `/api/ask` NDJSON stream, `/api/source`, `/api/brains` (+v2 jobs, `/events`), `/api/chats`, `/api/actions/draft`, `/api/actions/send`, `/api/graph`, `/api/stats`, `/api/extract` (+OCR ladder) |
| Verification **`[fixed]`** | `check_ui_react.py` is an acceptance suite over the **served** bundle (ask/stream/citations/files/draft/menus/keyboard/deep links/history, model calls intercepted); `tests/test_react_clerk.py` proves the Clerk-mode path with a no-token control; `tests/test_frontend_api_transport.py` and `tests/test_frontend_css_utilities.py` are static invariants. Those four run from `verify.sh` and the CI `ui` job. **Corrected 2026-10-04:** this row used to end "All of it runs from `verify.sh` and the CI `ui` job", which swept in `parity_gate.py` — a real pixel gate against the committed baselines in `docs/ui-review/baselines/`, and one that **no entrypoint runs** (`parity_gate` appears zero times in both `verify.sh` and `.github/workflows/ci.yml`; `docs/INDEX.md` records the same and leaves wiring-or-retiring as an owner decision). `parity_shots.py`/`parity_states.py` are capture helpers, also manual. Treat the pixel gate as something a human runs, not as coverage |

Not built (deliberately): no mobile app, no Electron/Tauri shell, no new CSS
design system. "React-native" here means *the React frontend as the native
desktop experience* — every legacy surface now renders through React.

---

## 2. The core architectural decision: the DOM contract

The legacy dashboard was already the polished artifact (a design system called
**"Deck"**). Rather than translate it into Tailwind and lose fidelity, React
was rewired to **render the same DOM the legacy JS rendered** — same ids, same
classes — so the original stylesheets apply unmodified:

```
frontend/src/main.tsx import order (mirrors :8000's cascade):
  1. index.css              — Tailwind v4 + token scaffold (@theme inline maps
                             shadcn color roles onto the legacy vars)
  2. design/deck.css        — the "Deck v4" layer (from the deleted
                             static/shell.css):
                             :root tokens, .shell sidebar, .app-main, .pop,
                             .settings-pop, scrollbars, light theme
  3. legacy/shell.css       — verbatim inline <style> from static/index.html:
                             two-mode layout, composer card, thread anatomy,
                             modals, rail, working log
  4. legacy/bridge.css      — the ONLY React-specific rule in the port:
                             #root { display: contents } (see below)
```

Why `#root { display: contents }`: the legacy CSS lays out the app by styling
`<body>`'s direct children (`aside.shell` is fixed; in home mode **body
itself is the centering flex container** and `.app-main` dissolves via
`display: contents` so `#home`, `form#f` and `#chips` interleave as one
column). React mounts into `#root`; dissolving that box reproduces the exact
parentage without touching the stylesheets.

**State is a body-class machine** (`frontend/src/App.tsx`, effect syncing to
`document.body`): `chatting` (thread mode vs home mode), `sb-collapsed`
(sidebar retracted), `switching` (in-place chat swap dimmer), `locked` (auth
gate), `detached` (scrolled away from bottom → shows `#jump-latest`). The
legacy CSS keys every mode off these classes; React only owns the truth.

**What this buys:** pixel parity is verifiable mechanically (pixel-diff gates,
§7); the design lives in two auditable CSS files, not in utility-class soup;
and future styling changes happen once, in CSS, for any future surface.

---

## 3. Deck v4 — the token anatomy (`frontend/src/legacy/deck.css`)

| Family | Tokens | Values (dark) |
|---|---|---|
| Canvas | `--bg --bg-2 --panel --panel-2 --panel-3` | `#1a1a1a → #333` stepped charcoal |
| Hairlines | `--line --line-2 --line-3` | white @ 8% / 13% / 22% |
| Hover washes | `--wash --wash-2 --wash-3 --watermark --scrim` | alpha-scaled whites |
| Type | `--sans --mono` | system sans (`15px/1.62` body), `ui-monospace` |
| Text | `--fg --fg-2 --muted --muted-2` | `#e9e9e9 → #949494` (muted-2 raised for WCAG) |
| Accent | `--accent --accent-2 --accent-soft --accent-dim --accent-glow --accent-ink --btn-ink` | falcon amber `#e8863b` — deliberately scarce: send button, active markers, ticks, focus ring |
| Semantic | `--good --bad --warn` | `#4ade80 / #f07070 / #e5c07b` |
| Geometry | `--radius(-sm/-xs) --shadow --shadow-lg --focus` | 14/10/7px; layered blacks; ring = accent-soft + glow |

Light theme is a **full second token set** on `html[data-theme="light"]`
(warm paper `#f7f5f2`, ink text, deeper amber `#b45309` for 4.5:1 text
contrast, `--btn-ink` inverted). Theme state lives in `localStorage
kestrel.theme` (`frontend/src/theme.ts`) — the same key the legacy shell
reads, so both UIs share one setting; `system` follows `prefers-color-scheme`
live.

The React token scaffold (`frontend/src/index.css`) maps these onto Tailwind
roles (`--color-background: var(--bg)`, `--color-primary: var(--accent)`, …)
so the handful of shadcn-derived components (buttons, dialogs, dropdowns in
`components/ui/`) inherit the Deck palette instead of introducing a second
one. One cascade subtlety, verified against `:8000`: the light theme must NOT
re-derive `--good/--warn` (legacy light overrides only `--bad`; the rest
inherit the dark `:root`) — `index.css` carries a comment pinning this.

---

## 4. Surface-by-surface anatomy (what is built, where it lives)

All handler wiring lives in `frontend/src/App.tsx` unless noted. The DOM
names below are the load-bearing contract with the stylesheets.

### 4.1 Sidebar — `aside.shell` (`components/Sidebar.tsx`)
- **Brand row**: `.mark` amber diamond, `.name/.sub`, `«` retract
  (`.sb-collapse`) → `body.sb-collapsed` + persisted `localStorage
  kestrel.sb.collapsed`; re-opened by the floating `☰` (`.sb-toggle`), which
  doubles as the off-canvas toggle under 820px (`.shell.open`).
- **Nav**: exactly the legacy items — New chat, New brain (opens
  `CreateBrainDialog`), Brains (in-app `BrainsPage`), Graph (in-app
  `GraphView`). Connectors lives in the gear menu, as on :8000.
- **Chats** (`#sb-chats`): `.chats-head` + `#sb-viewmenu` pop (grouped-by-brain
  vs timeline; sort by updated/created — persisted `kestrel.sidebar.view`);
  `.brain-row` folders (caret, fold state persisted, `.group-del` two-step
  armed wipe); `.nav-item.chat-item` rows (30-char titles, `.row-del` two-step
  armed delete, `.chat-time` relative stamps in timeline mode).
- **User area** (`.sb-user`, clerk mode only): avatar initials/image,
  name+email → account modal; gear → `.settings-pop` (language, theme, usage,
  upgrade, connectors, account, disconnect) with sub-popovers. **`[fixed]`** The
  pop is anchored from the gear's rect and closes on outside click/Escape (it
  was unpositioned with `onClose` ignored), and Usage/Upgrade are the real modals
  over `/api/usage` and the tier table (they were toasts).
- Known delta: the legacy "gliding hover highlight" (`.sb-slide`,
  mousemove-driven) is not ported; rows fall back to plain `:hover` washes.

### 4.2 Home (`#home`) and the two-mode layout
`body:not(.chatting)` turns body into the flex column: `.watermark` (150px
diamond in `--watermark` alpha) + `.greeting` (30px/550), then `form#f`
(order 2) and `#chips` (order 3) as one 680px column, offset by the sidebar
width. Asking anything flips `body.chatting`: home hides, `#thread-wrap`
appears, the composer docks bottom-fixed.

### 4.3 Composer — `form#f > .field > .bar-card.bar-anchor`
- **Top row**: `#brainswitch` (grid glyph + `#brainname` label + chevron) →
  `#brainmenu` pop ("Ask in" + brains with `· demo` suffix + tick on current
  + `＋ New brain…`); `#menu2-toggle` (`⋯`) → `#menu2`.
- **`#menu2`** (legacy ids preserved for DOM/test parity): question count
  (`fmt('menu.questions')`), Copy transcript, Add documents (opens the files
  sheet), Export Markdown/plain-text/Word/PDF (client-side generation incl.
  self-printing-PDF iframe), armed two-step Clear conversation (server DELETE
  + reset).
- **Attachments** (`.atts#pending`): 64×64 thumbs (image preview or
  `.att-file` glyph+name, `.x` remove). On send: text-like files ride
  client-side (`buildContext`, 6 KB cap), binaries go through `/api/extract`
  (OCR fallback announces itself), and everything ingestible is appended to
  the current brain — future questions can cite them.
- **`#q`**: auto-grow to 140px, Enter submits / Shift+Enter newlines; `#go`
  is a 34px circle that flips send → stop (`.stop`, filled square) while
  streaming — never disabled (a legacy lesson: a disabled submit once locked
  the page).

### 4.4 Thread — `#thread-wrap > .wrap > #thread`
- `.turn.user > .bubble`: right-aligned card (85% max), `white-space:pre-wrap`.
- `.turn.bot`: **`.working` log first, then the bubble** — the bot turn is
  created *on submit* (with `.bubble.streaming` cursor and the working log),
  not on first chunk, matching :8000.
- **Working log** (`.working`): server-driven steps only, label-mapped via the
  legacy `stageLabel` rules (`Smalltalk:` / `Orchestrator: planning` /
  `Router: general chat` / `Delegating to` → friendly forms), per-step
  measured durations (`✓ label · 0.5s`, server `ms` honored), live step gets
  the spinning `◌` marker; on completion it collapses into its header
  (`collapsed` + `toggle` chevron, click to re-expand), `· stopped` appended
  if aborted.
- **Bubble**: `.rendered` (markdown via lazy `components/Markdown.tsx`) with
  the legacy element styling (accent list markers, uppercase table heads,
  amber `strong`); `.streaming` paints the blinking block cursor.
- **`.srcs`** citation chips → open `#source-modal` (below). Unresolved
  citations are marked, never guessed.
- **`.msg-acts`** hover row (opacity 0 → 1 on `:hover`/focus-within): copy
  (answer + sources line, transient `.copied` green), quiet thumbs feedback
  (`.fb-on`), timestamp — plus **one deliberate addition**: a mail action
  (§4.7).
- **Left rail** (`#rail` + `#rail-tip`): one tick per user turn, staggered
  `railIn` entrance, scroll-linked `.here` marker (nearest tick to the 35%
  viewport line), hover preview (question + 110-char answer extract), click
  jumps. `#jump-latest` pill appears via `body.chatting.detached`.

### 4.5 Source modal — `#source-modal` (`components/SourceModal.tsx`)
Centered sheet: `.nm` filename, `.where` origin line (`from your upload /
from the corpus · N chars` — the resolver's honest provenance), Copy/Close,
mono `<pre>` with the cited passage highlighted via whitespace-flattened
`<mark>` search. Escape/backdrop dismiss. Unavailable sources say so verbatim.

### 4.6 Files sheet — `#files-sheet` (`components/FilesSheet.tsx`)
Add-documents-to-this-brain flow: dashed `.drop` zone (click/drag, `.over`
state), format/size gates (40 files · 5 MB, per-file notes), per-file verdict
rows (`.ok`/`.bad` + `added/failed/skipped` from `POST /api/brains` append),
then **real pipeline progress** streamed from `/api/brains/<name>/events`
(`poll` state → `ready ✓ / failed / timeout / error`) into `.pipeline`, and a
`.done` summary line. The demo brain is read-only and the sheet says so.

### 4.7 Draft box — `#draft` (`components/DraftBox.tsx`) — *new capability*
The legacy shell carried `#draft` CSS but never rendered the surface; the P6
APIs (`POST /api/actions/draft`, `POST /api/actions/send`) existed unwired.
React completes it: a hover-revealed mail action on the last answer drafts an
email from the Q/A/sources pair and opens the box below the thread —
recipient in the `.head`, editable mono body, Copy / Open in mail (mailto) /
**Send** / Close. Send is an explicit approval gate: unconfigured transports
return the server's own 503 words as a toast. (Draft generation itself needs
the LLM; with generation routes down it fails honestly.)

### 4.8 Overlays & gates
`#switch-fx` (spinner + app dim during in-place chat switch),
`#restore` (cover while a `?chat=` restore is in flight — the empty home state
never flashes), `#auth-gate` (Clerk `openSignIn` modal over the app;
`body.locked` blurs `.app-main`/`form#f`). Clerk is loaded from CDN
(`lib/clerk.ts`), sessions are the signed-in truth, and **`[fixed]`** every API
call carries a Bearer token via `lib/api.ts` `apiFetch` — awaited Clerk boot, a
token minted **per request**, one forced-refresh retry on 401, and an honest
error state instead of empty data when the server refuses (previously a
mount-time hook used in three places, so `/api/ask`, `/api/chats`, `/api/brains`
and friends 401'd in clerk mode). The gate installs Clerk's card inline inside
`#clerk-mount`; it used to open a modal over an empty card.

### 4.9 React-first pages (beyond the legacy shell)
- **`BrainsPage`** (`components/BrainsPage.tsx`): brain list with live graph
  stats (`/api/stats` nodes/edges, lazy per-row), demo/system badges, Open /
  Graph / Add-documents actions, and the **two-step armed delete** (6s
  disarm timer) for non-demo brains. Reached from the sidebar; the legacy
  `/brains` page stays reachable as `?view=legacy-brains`.
- **`GraphView`**: simplified in-app graph from `/api/graph` with an honest
  labeled link to the full legacy `/graph` page (the deliberate delta).
- **`UploadPage`** (v2 job API, per-file progress) and the `LegacyMount`
  escape hatches (`?view=legacy-upload|legacy-graph|legacy-brains`) exist but
  are intentionally not in the nav.
- **`CreateBrainDialog`** (name + documents → v2 job), **`Connectors`** view
  (transport status pills), `CreateBrainDialog`/`SlackAccessDialog` round out
  the management surfaces.

---

## 5. UX advancements over the legacy dashboard

Beyond restoring parity, these are net-new or repaired behaviors:

1. **Durable conversations, correctly** — every finished ask persists to
   Postgres (legacy saved only on some paths; React's first cut saved only on
   errors — fixed). Saves run in a streaming-flip effect so the last chunk is
   never lost. Reload **resumes the remembered chat per brain**
   (`sessionStorage kestrel.currentChat.<brain>`, `?new=1` clears) — legacy
   behavior, previously missing in React.
2. **Draft-from-answer** (§4.7) — a real drafting→approval→send pipeline
   where legacy had nothing.
3. **In-place everything** — chat open, brain switch, and view changes are
   SPA state moves (deep-links kept: `?brain= ?chat= ?new= ?view=`), with the
   `#switch-fx` swap instead of page reloads.
4. **Honest states as a policy** — citations that can't resolve are labeled;
   read-only demo brains say so; unconfigured email/Slack sends surface the
   server's exact 503; failed generation prints the provider's error instead
   of spinning.
5. **Two-step armed destructive confirms** everywhere (chat, brain-chat group,
   brain page, clear-conversation) — consistent disarm timers, `.armed`
   styling.
6. **Accessibility**: `:focus-visible` ring token, aria-labels on all icon
   controls, keyboard paths (Enter/Shift+Enter/Esc/Tab into hover rows via
   `:focus-within`), `aria-live` thread, skip link.
7. **i18n & theme as first-class**: 6 languages through the shell
   (`lib/i18n.ts`, same key space as legacy `KI18N` — German spot-checks
   match :8000 exactly), light/dark/system with live OS-follow.
8. **Self-advantaging test surface**: the UI is auditable by machines
   (§7) because the DOM is a stable contract — the smoke suite caught a real
   regression (view/sort pop not closing on outside-click/Escape) during the
   port.

---

## 6. Interaction & motion inventory (all legacy-faithful)

`rise` turn entrance · `pop` menu spring · `sheet` modal scale · `railIn`
staggered rail ticks · `blink` streaming cursor · `spin` (working log /
switch-fx / restore) · hover-reveal `msg-acts` · armed-confirm color flips ·
`prefers-reduced-motion` collapses all of it to 0.01ms (both stylesheets).

---

## 7. Verification methodology (how to audit the claims)

| Gate | Command | Expected |
|---|---|---|
| Unit/battery (backend untouched) | `./verify.sh --quick` | 25/25, 13/13, 90/90, 10/10, 4/4 |
| React UI smoke (clicks every control, fails on console errors) | `./verify.sh` — it points `check_ui_react.py` at the battery's own mock tier on `:$KESTREL_VERIFY_PORT` (8020). Do not run it against `:5174` (no API behind it) or against live `:8000`: **the suite saves chats**, and that is the one write this product's demo database must not receive | all views clean |
| Pixel regression | `python3 parity_gate.py` | 0.000% strong-pixel drift against `docs/ui-review/baselines/<platform>/` (fails above 0.5%) |
| Side-by-side vs legacy (capture only) | `python3 parity_shots.py <tag>` | PNGs for a human to compare — not a gate |
| Stream-shaped flows (citations, draft, save) | intercepted NDJSON via Playwright (`parity_states.py`, §patterns in repo chat logs) | identical rendering on both UIs with identical fixtures |

Requires the stack up: `./ops_stack_up.sh` (colima → compose → :8000), lab
compose + `:8010` (auth-off twin used as the comparison target), Vite
`KESTREL_API=http://localhost:8010 npm run dev` on `:5174`.

---

## 8. Known deltas & open decisions (so the review sees them)

- **Dropped for parity** (React-only extras): sidebar chat search; the old
  MessageActions email/steps row (superseded by the draft surface). **`[fixed]`**
  The `.sb-slide` gliding nav highlight **is** ported and mounted (it existed but
  was imported by nobody).
- **Open decision**: `FilesSheet` streams the legacy `/events` pipeline;
  `UploadPage` speaks the newer v2-jobs API (per-file progress) which the
  spec says supersedes it. Unifying is frontend-only but deliberately
  diverges from :8000 — owner's call.
- **Blocked on externals**: generation routes are down until 6 Oct — asks and
  draft-generation fail honestly; the signed-in Clerk walkthrough of :8000 is
  pending (gate verified signed-out only).
- **Honest docs**: `docs/FRONTEND_FIX_PLAN.md` (the verified findings and the
  phased fix — §6 carries execution status), `docs/REACT_VS_LEGACY_GAP.md` (port
  plan + execution status), `docs/LEGACY_SHELL_SPEC.md` (the legacy source of
  truth), `docs/LEGACY_TO_REACT_PARITY.md` (feature matrix, **superseded** — it
  predates the port's completion).

*One vocabulary note for the review: this is a React (web) frontend — the
desktop dashboard. No React Native (mobile framework) code exists or is
planned; "native desktop" here means the React app is the product's primary
desktop experience.*
