# Kestrel frontend (React + Vite)

This is the product frontend. `python app.py` serves the built bundle from
`frontend/dist` at `/` when `KESTREL_UI=react` (the default); `KESTREL_UI=legacy`
serves the old `static/index.html` dashboard instead, and the legacy pages
(`/graph`, `/brains`, `/upload`) stay reachable either way.

## Build and serve

```bash
./ops/build_frontend.sh              # npm ci + tsc + vite build → frontend/dist
./ops/build_frontend.sh --no-install # reuse node_modules (fast loop)
python3 app.py                       # serves dist at http://127.0.0.1:8000
cd frontend && npm run dev           # Vite dev server (proxies /api to KESTREL_API)
```

`frontend/dist` is **committed**: the app tier has no Node (Render installs only
`requirements.txt`; `ops_stack_up.sh` just runs `python app.py`). The build is
deterministic — CI rebuilds and runs `git diff --exit-code -- frontend/dist`, so
a stale bundle fails the build instead of shipping.

## Invariants (each one exists because it was broken once)

1. **One authenticated transport.** Every `/api` call goes through `apiFetch` in
   `src/lib/api.ts`: it awaits Clerk boot, mints a token *per request* (Clerk
   tokens last ~60s), and retries once on 401 with a forced refresh. A bare
   `fetch()` or an `"/api/..."` literal anywhere else fails
   `tests/test_frontend_api_transport.py`. Top-level OAuth navigations are the one
   exception and must carry a `transport-exempt` comment.
2. **The legacy stylesheets own the design.** `main.tsx` imports, in order:
   `index.css` (Tailwind + Deck role aliases) → `legacy/deck.css` (tokens,
   sidebar) → `legacy/shell.css` (the ported inline shell styles) →
   `legacy/fonts.css` (self-hosted Inter, so `#q`, `.bname` and `code` — which
   read Deck's `--sans` directly — use the same face) → `legacy/bridge.css`
   (`#root { display: contents }`, the only React-specific rule). Components
   render the same ids/classes the legacy DOM used.
3. **Colour roles are declared, not assumed.** `@theme inline` in `index.css`
   maps Deck tokens onto Tailwind roles (`--color-panel`, `--color-line-2`,
   `--color-fg-2`, …). `--color-accent` is the **brand amber**; shadcn hover
   surfaces use `--color-accent-surface`. A utility with no role emits no CSS,
   which is invisible in review — `tests/test_frontend_css_utilities.py` fails on
   it.
4. **Tailwind scans `src/` only** (`@import "tailwindcss" source("../src")`).
   Without the pin it also scans the committed `dist/`, so each build consumed the
   previous one's class strings and every asset hash moved.
5. **oxlint ignores `dist/**`** for the same reason.
6. **State the legacy shell put on `<body>`** (`chatting`, `sb-collapsed`,
   `switching`, `locked`, `detached`) is synced from React effects; the CSS keys
   every mode off those classes.

## Verification

```bash
./verify.sh                       # battery + frontend static gates + UI acceptance suite
./verify.sh --quick               # skips the browser suites
KESTREL_CLERK_GATE=1 DATABASE_URL=postgresql://kestrel:kestrel@localhost:5434/kestrel \
  ./verify.sh                     # + the Clerk-mode gate

python3 check_ui_react.py --base http://127.0.0.1:8000   # acceptance suite
python3 tests/test_react_clerk.py                        # auth on, with a control run
python3 tests/test_frontend_api_transport.py             # transport invariant
python3 tests/test_frontend_css_utilities.py             # token invariant
python3 parity_gate.py [--update]                        # pixel regression gate
cd frontend && npm run lint && npx tsc -b
```

`check_ui_react.py` intercepts the model calls with canned NDJSON, so it is
deterministic and free: ask/stream/per-turn working log, citations → source
modal, files sheet verdicts, draft box, menus, keyboard, brains page, deep links
and Back/Forward.

## Accepted lint warnings (10, all reviewed)

`npm run lint` reports **0 errors** and these warnings. They are known, benign,
and listed here so a new one shows up as a change:

| Rule | Where | Why it stays |
|---|---|---|
| `react/set-state-in-effect` (6) | `Animations.tsx` ×2, `BrainsPage`, `Connectors`, `FilesSheet`, `GraphView` | loading/reset state set at the top of a fetch effect, and a prefill-from-prop sync. A reducer would not change behaviour. |
| `react/only-export-components` (2) | `ui/badge.tsx`, `ui/button.tsx` | the shadcn convention (`badgeVariants`/`buttonVariants` exported next to the component); affects fast-refresh granularity only. |
| `react-hooks/exhaustive-deps` (1) | `App.tsx` persist effect | `persistChat` is called conditionally; it is a real dependency and the disable directive documents that. |
| `react/immutability` (1) | `Animations.tsx` `tryMount` | the Clerk mount retry closure — flagged while initialised, verified correct in the browser (the gate mounts inline). |
