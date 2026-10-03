# FRONTEND FIX PLAN — making React the frontend the product actually serves

_Written 2026-10-03, immediately after `docs/REACT_UIUX_ADVANCEMENTS.md`. Every
claim below was verified against code (`file:line`) or against a running process;
where a check was run, the command and its result are given so it can be repeated.
**Nothing in this plan has been implemented yet** — it is the work order for
EXECUTION_PLAN.md Phase 9 ("React as the supported frontend", F6 still open)._

Context read for this plan: `docs/REACT_UIUX_ADVANCEMENTS.md`,
`docs/REACT_VS_LEGACY_GAP.md`, `docs/LEGACY_TO_REACT_PARITY.md`,
`docs/UI_POLISH_REVIEW*.md`, `EXECUTION_PLAN.md` (Phase 9 + F6), all of
`frontend/src/**` and `frontend/src/legacy/*.css`, `app.py` (pages, auth, ask,
graph), `static/index.html` / `shell.js` / `ui.js` / `auth.js`, `check_ui.py`,
`check_ui_react.py`, `parity_*.py`, `detect_frontend.py`, `verify.sh`,
`.github/workflows/ci.yml`, `render.yaml`, `frontend/.gitignore`, `.env`.

---

## 0. The one-paragraph version

The React port is real, and the DOM-contract approach worked. It is also **not the
frontend the product serves, and it cannot work in the product's own
configuration**. At `:8000` — the live `.env`, `AUTH_MODE=clerk` — `/` still
returns `static/index.html`, `frontend/dist` is mounted nowhere and its assets 404,
and nearly every API call the React app makes (`/api/ask`, `/api/chats`,
`/api/brains`, `/api/source`, `/api/extract`, `/api/actions/*`, `/api/graph`,
`/api/connectors/*`) goes out **without an `Authorization` header**, so it 401s.
The port has looked green only because its dev server proxies to the auth-off lab
twin (`:8010`), where `require_tenant` waves everything through. Underneath that,
three ask-path defects would still be wrong even with perfect auth: a 401/500 body
is rendered as a **permanently empty answer** (`res.ok` never checked), **no
conversation history is sent** so every follow-up is a cold start, and a stream
parse error surfaces as a fake transport failure. Around them sit ~18 verified
parity regressions — including a graph view that silently renders the **demo**
brain's graph for every brain (`?brain=` vs the API's `dataset=`), a language
switch that changes nothing until reload, and an auth gate that does not cover the
app. Fixing the frontend means: serve it, authenticate it, make the ask path
honest, close the visible parity regressions, and make verification that can
actually fail run in CI.

---

## 1. Verified reality

### 1.1 What is actually served today — not React

| Fact | Evidence |
|---|---|
| `/` serves the legacy dashboard | `curl http://127.0.0.1:8000/` → `/static/shell.css`, `/static/ui.js`, `/static/auth.js`. Route `app.py:1825-1828` → `_page("index.html")` (`app.py:1808`) |
| The React build is mounted nowhere | Only mount: `app.mount("/static", NoCacheStaticFiles(directory=static))` (`app.py:140`). `frontend/dist` is referenced **nowhere** in server/build/CI code |
| Its assets 404 on the real server | `/assets/index-*.js`, `/assets/index-*.css`, `/favicon.svg`, `/icons.svg` → **404** on `:8000` (they exist only under Vite, which serves `frontend/public/`). A 404 favicon is a console error and would fail the smoke suite's console-clean assertions (`check_ui_react.py:133,168,180`) |
| The build is not in git and nothing consumes it | `frontend/.gitignore:12` ignores `dist`; CI builds it (`ci.yml:15-19`) after `verify.sh` and discards it — no `upload-artifact`, no assertion it exists |
| CI builds/verifies the wrong UI | `ci.yml:13-14` runs `./verify.sh --quick`, which skips the UI suite entirely (`verify.sh:106-108`); the full run calls `check_ui.py` — the **legacy** suite (`verify.sh:109`) |
| `check_ui.py` is dead on this machine | `check_ui.py:25` hardcodes `NODE_BIN=/Users/_iayushsharma_/.workbuddy-ai/…/node_modules/.bin` (does not exist), needs `playwright-cli` (not on PATH) and webkit (`:78`). So a full `./verify.sh` cannot pass; the recorded "battery green" is `--quick` only, and **neither frontend currently has a working browser suite** |
| Auto-detection cannot see the running React app | `detect_frontend.py:72` probes `5173`/`8000`; the dev server runs on **5174** (`ps`; `vite.config.ts:16` still says 5173). Live: `python3 detect_frontend.py` → `legacy`, so `check_ui_react.py` exits "No React frontend detected" unless given `--base` |
| The "served from `/static/app`" comment is fiction | `frontend/vite.config.ts:6-7`; that string appears nowhere else, and `/static/app/` is a verified 404 |
| The bundle is not reproducible from a clone | no npm step in `render.yaml:26`, no Docker/compose step; `ops_stack_up.sh:17` just runs `python3 app.py` |
| README already contradicts the advancements doc | `README.md:286-288`: "`static/` remains the zero-build fallback UI" |

**Consequence.** `REACT_UIUX_ADVANCEMENTS.md` §1 — "the `frontend/` React
application … has replaced the legacy `static/index.html` dashboard as the
product's desktop frontend" — is true of the dev server only.

### 1.2 P0 — the app is unauthenticated in the live configuration

`.env` sets `AUTH_MODE=clerk`; `require_tenant` (`app.py:184-206`) returns **401**
without a valid Clerk JWT in `Authorization`. Measured now:

```
curl -o /dev/null -w '%{http_code}' :8000/api/brains   → 401
curl -o /dev/null -w '%{http_code}' :8000/api/chats    → 401
curl -o /dev/null -w '%{http_code}' :8010/api/brains   → 200   (auth-off lab twin)
```

Legacy solves this globally: `static/auth.js` exposes `KestrelAuth.authHeaders()`,
which awaits boot and mints a token **per request** (`static/auth.js:73`; Clerk
session tokens are short-lived, ~60 s), and every legacy call awaits it
(`static/index.html:1224-1226` and ~20 call sites). React has a mount-time hook,
`useAuthHeaders()` (`frontend/src/lib/api.ts:12-32`), used in only three live
places (`FilesSheet.tsx:30`, `BrainsPage.tsx:51` delete, `UploadPage.tsx:160,223`)
and one dead file. Everything else sends nothing:

- ask `App.tsx:506`; extract `:120`; attachment ingest `:497`; draft `:797`
- chats: list `lib/api.ts:59`, fetch `:78`, save `:89`, deletes `App.tsx:742,751,758,761`
- brains: list `lib/api.ts:37`, v2 create `:107`, job poll `:119`, stats `BrainsPage.tsx:235`
- `SourceModal.tsx:26`, `GraphView.tsx:25`, `Connectors.tsx:48,52,67`,
  `SlackAccessDialog.tsx:22`, `DraftBox.tsx:31`

Two compounding defects: the token is **cached at mount** (stale within a minute,
and `{}` if the CDN `clerk.browser.js` resolves after mount, `lib/clerk.ts:12-14`),
and a 401 renders as **empty data** — `useBrains` `.catch(() => {})`,
`useChats` `.catch(() => setChats([]))` (`lib/api.ts:48,71`) — so the app says
"No saved chats yet" when the truth is "not authorised".

### 1.3 P0 — the ask path cannot report failure

| Legacy | React |
|---|---|
| `if (!res.ok \|\| !res.body) throw new Error('HTTP ' + res.status)` (`static/index.html:1383`) | `const res = await fetch(...)`, then `res.body!.getReader()` (`App.tsx:506-507`) — a 401/500 JSON body has no trailing newline, is swallowed by the buffer tail, and the user gets a **permanent empty bot bubble with no error** |
| per-line `try { ev = JSON.parse(line) } catch { continue }` (`:1398`) | bare `JSON.parse(line)` (`App.tsx:518`) — one bad line aborts the stream and is reported as "Could not reach the server: Unexpected token …" (`:572-575`) |
| abort with partial text appends `_(stopped.)_`, keeps sources + actions, saves (`:1461-1473`); empty stream → "No answer returned for that question." (`:1455`); no text on abort → "Stopped before any answer arrived." (`:1475`) | `AbortError` fully swallowed (`App.tsx:567`); no terminal-state copy at all; a non-abort error with existing text **appends a brand-new bot turn** (`:569-576`) |
| failures use `bubble.className = 'bubble err'` (`:1423`, CSS `shell.css:258`) | `"⚠️ " + message` is written **into the markdown answer** (`:541-548`) — failures read as model output, never red |

### 1.4 P0 — follow-up questions have no referent (history is never sent)

Legacy builds `history` from the last 3 turns and passes it as `context`
(`static/index.html:1237-1239,1379`). React sets `context` **only when files are
attached** (`App.tsx:481-489`). The backend documents the consequence at
`app.py:1164-1194` ("without it, every turn is a cold start and a follow-up
question has no referent") and prepends it at `:1194`. So in the React UI,
"and who signs it off?" is a cold-start question. This is a product-correctness
bug, independent of the port's visual work.

### 1.5 Silent styling failure — ~120 Tailwind classes emit no CSS

`index.css:8-41` maps only a subset of Deck tokens into Tailwind
(`--color-background/foreground/card/popover/primary/secondary/muted/accent/
accent-dim/destructive/ok/ok-dim/warn/warn-dim/border/input/ring/sidebar*`).
Components use 120+ utilities with no token behind them — verified against the
built bundle (`dist/assets/index-*.css` contains `.bg-card`, and no `.bg-panel`,
`.border-line-2`, `.text-fg-2`, `.bg-wash*`, …):

| Dead utility | Uses | Where it shows |
|---|---|---|
| `bg-panel`, `bg-panel-2`, `bg-panel-3` | 15 / 20 / 2 | `App.tsx:1270,1278,1290,1298` (language + theme submenus — transparent and borderless), `CreateBrainDialog.tsx:78,101`, `GraphView.tsx:77`, `Connectors.tsx:34` |
| `border-line`, `-line-2`, `-line-3` | 27 / 19 / 1 | `LegacyMount.tsx:31,38`, `Connectors.tsx:34`, `Animations.tsx:374` |
| `bg-wash`, `bg-wash-2`, `bg-wash-3` | 10 / 5 / 9 | settings/sidebar hovers, `Connectors.tsx:166` |
| `text-fg`, `text-fg-2`, `text-muted-2`, `text-accent-2`, `text-bad` | 12 | `App.tsx:1278,1298` + dead components |

Related token hygiene: `index.css:43-73` re-declares Deck's `:root` (duplicate
source of truth); `--warn` is defined twice (`:64` `#fbbf24`, `:71` `#e5c07b`) and
then overridden again by `deck.css:69`, so the polish spec's warning colour never
wins; `Inter` is declared as the sans stack (`:40`) but never loaded anywhere in
`frontend/` (marketing ships `@fontsource-variable/inter`; the shell actually
renders Deck's `--sans`, `deck.css:43`); `--ink` is referenced at
`GraphView.tsx:120` and does not exist.

### 1.6 P1 — behavioural regressions a user will hit (verified in code)

| # | Gap | Legacy | React |
|---|---|---|---|
| R1 | Back/Forward desync | nav items are real `<a href>` (`shell.js:40-47`) | five `history.pushState` (`App.tsx:611,620,628,640,276`), **zero** `popstate` listeners → Back changes the URL, the view never moves |
| R2 | Language switch does nothing until reload | `t()` reads a live `lang`; every surface re-renders (`ui.js:524-527`, `shell.js:1023-1036`) | `setLang` mutates a module var + fires `kestrel:lang` (`i18n.ts:939-945`); the only listener sets `greet` to the **same hardcoded English** value (`App.tsx:326-330`, `api.ts:125-128`) → React bails out; chips are frozen at module scope (`App.tsx:57-68`); nav labels hardcoded (`Sidebar.tsx:272-275`), settings items hardcoded (`Animations.tsx:452-484`). **Runtime-proven** (see §1.9) |
| R3 | Working log only exists on the last answer | every turn keeps its own collapsed log with per-step durations (`static/index.html:1670-1733`) | `workingHere = isLast && workSteps.length > 0` (`App.tsx:843`); `startWork()` clears (`:427`) → previous logs vanish |
| R4 | Streaming yanks the viewport down | `stick` honoured; instant scroll (`:1076-1084,1404`) | smooth `scrollBottom()` on **every chunk** (`App.tsx:529,581`); `jumpVisible` computed but never gates scrolling (`:355`) |
| R5 | Restored turns get a fabricated "now" timestamp | stored `at` used (`:1142`), mapped on restore (`:971,997,1027`) | `new Date().toLocaleTimeString()` at render (`App.tsx:928`); `fetchChat` drops `at` (`api.ts:81-85`) |
| R6 | Restored attachments disappear | `attachments` persisted and re-rendered (`:1245,1251,1058,1564-1590`) | `Turn` has no `attachments` field (`api.ts:5-10`); nothing renders them |
| R7 | No attachment size gate / no persistence | >8 MB refused; ≤1.5 MB snapshotted as data URLs so they survive reload (`:1523-1532`) | `.slice(0,6)` only (`App.tsx:668-671`) |
| R8 | Sidebar list is current-brain-only and empties off the chat view | list spans every brain and renders on all four pages (`shell.js:55-68,128-214,414-493`) | `useChats(view === "chat" ? brain : null)` (`App.tsx:392`) → "No saved chats yet" on Brains/Graph/Connectors, and "Grouped by brain" can only ever show one folder |
| R9 | `?new=1` never cleared, `?chat=` never written after asking | `rememberChat()` (`:636-648,671`) | `newChat` sets `new=1` (`App.tsx:636-643`); `persistChat` never touches the URL (`:455-464`) → reload after a fresh ask shows an empty thread although the chat was saved |
| R10 | Switching chats does not abort the running stream | `CONTROLLER.abort()` before the swap (`:1965-1968`) | `openChat` never aborts (`App.tsx:622-635`) → the in-flight answer is written into the newly opened thread |
| R11 | Composer stuck in "stop" through citation resolution | `finalize()` on `{stage:"done"}` frees the composer (`:1256-1281,1408-1417`) | `streaming` clears only in `finally`; `done` is explicitly skipped (`App.tsx:549,578-585`) → Enter aborts while citations resolve |
| R12 | Brain switcher leaks system brains, unsorted, no mid-chat confirm | filters `!is_system`, demo-first sort, two-step "fresh chat?" (`:760-763,731-737`) | unfiltered/unsorted (`api.ts:39-45`, `App.tsx:1147-1159`); switches immediately (`:613-621`) |
| R13 | Every ask's first working-log row claims retrieval was bypassed | only `ev.stage === 'step'` renders a row (`:1405-1407`) | condition also matches `{stage:"start"}` (`app.py:1207`) and maps it to `stage.router_chat` = "General chat — bypassing retrieval" (`App.tsx:549-554`, `i18n.ts:128`) |
| R14 | Graph view silently shows the **demo** graph for every brain | `graph.html:606-607` sends `?dataset=` | `GraphView.tsx:25` sends `?brain=`; `/api/graph` reads only `dataset` (`app.py:1252`), so `dataset=None` → demo. **Runtime-proven** (see §1.9) |
| R15 | Settings pop is unanchored; Usage/Upgrade are toasts | positioned from the gear rect (`shell.js:581-585`), real `/api/usage` modal (`:640-680`) and pricing tiers (`:682-704`) | no positioning and `onClose` ignored (`Animations.tsx:424-490`); `toast.info(...)` (`App.tsx:1260-1261`); `.km-scrim/.u-table/.tiers` CSS and `/api/usage` exist unused |
| R16 | Sign-in gate does not cover the app | covering `#clerk-mount` gate + blur (`static/index.html:216,2166-2211`) | `<AuthGate>` with no children, only `Clerk.openSignIn()` behind a 100 ms poll + 10 s blind timeout (`App.tsx:1252`, `Animations.tsx:287-330`); the component that *does* mount a covering card (`AuthGate.tsx`) is dead |
| R17 | Connectors lost their jobs | Slack/Gmail import forms, posting, `needs_reconnect`/soon pills (`shell.js:706-848,878-985`) | Slack configure + workspace disconnect only (`Connectors.tsx:82-197`) |
| R18 | `.sb-slide` gliding hover is unmounted | live (`shell.js:365-406`, `deck.css:186-196`) | `SlideRail` exists but no one imports it (`Animations.tsx:29-81`); `sb-slide-on` never set |

### 1.7 P2 — hygiene, in one list

Created-sort is a no-op (`api.ts:63-68` drops `created`; `Sidebar.tsx:120,213`);
`navigator.clipboard` has no insecure-context fallback (`App.tsx:730,773`); demo
folder label misses `company_brain` (`Sidebar.tsx:239`); rail stagger uses the
turn index, no resize listener (`App.tsx:1206`); `aria-live="polite"` on
`#thread` re-announces every chunk (`:1004`); Escape no longer closes the settings
menu and the source modal lost backdrop-click close; textarea height never resets
after send (`:675-680`); chips send immediately instead of filling the composer
(`:1177`); clear-conversation copy/arming differs (`:736-746,1140-1142`) and the
draft box stays open; unnamed sources become a chip literally labelled "source"
(`:531-534`); FilesSheet replaces notes instead of appending (`FilesSheet.tsx:43`);
theme submenu can never tick "System default" (`App.tsx:693,1302`); `?brain=` is
not forwarded by in-app nav (`App.tsx:606-612`); nav/chat links are `href="#"` so
⌘-click/middle-click cannot open a new tab (`Sidebar.tsx:169,184`); `LegacyMount`
views are unreachable, double-chrome (React sidebar + the iframe's own sidebar),
and their comment claims the React sidebar hides; `document.title` never tracks the
brain; no `crypto.randomUUID` fallback outside a secure context (`App.tsx:456`);
`i18n.ts:556` has a corrupted French string that swallows `usage.sub`; dead
components (`PromptBox`, `WorkingLog`, `MessageActions`, `SuggestionChips`,
`ExportMenu`, `SourceDrawer`, `GraphPage`, `UploadPage`, `AuthGate`,
`SettingsMenu`, ~15 `ui/*` primitives, and ~12 unused exports inside
`Animations.tsx`), two of which hold the repo's only lint **errors**
(`UploadPage.tsx:160,223`).

### 1.8 Runtime checks run for this plan (repeatable)

```bash
# 1. React is unauthenticated in the live config (the P0)
curl -o /dev/null -w '%{http_code}\n' :8000/api/brains      # 401   (AUTH_MODE=clerk)
curl -o /dev/null -w '%{http_code}\n' :8010/api/brains      # 200   (auth-off lab twin)
# 2. The served product is the legacy page, and the React assets 404
curl -s :8000/ | grep -c 'ui.js'                            # 1  (legacy shell)
curl -o /dev/null -w '%{http_code}\n' :8000/assets/index-CAqIOa5l.js   # 404
# 3. The graph param mismatch (R14) — same API, two names, different data
curl -s ':8010/api/graph?brain=kestrel_full'   | jq '.nodes|length'   # 93  (demo graph!)
curl -s ':8010/api/graph?dataset=kestrel_full' | jq '.nodes|length'   # 233 (the real brain)
# 4. The language switch is a visible no-op (R2) — Playwright, dev server on :5174:
#    goto '/', inner_text('body'), then
#    evaluate("async () => { const m = await import('/src/lib/i18n.ts'); m.setLang('de'); }")
#    → body text is byte-identical before/after, greeting stays "Evening, how can I help?"
#      (localStorage['kestrel.lang'] does become 'de', so only a reload shows German)
# 5. Auto-detection cannot see the running React app
python3 detect_frontend.py                                  # {"verdict": "legacy"}
```

### 1.9 What is genuinely good — do not rebuild it

The DOM contract works: `main.tsx` cascade order, `bridge.css`
(`#root{display:contents}`), the body-class state machine, the thread/composer/
rail/working-log/files-sheet/source-modal/draft surfaces, two-step armed confirms,
theme parity including the light-theme `--good/--warn` subtlety, honest
provider-error copy on the draft path, and the Clerk appearance variables. The
build is green (`tsc -b && vite build`, 299 ms, 502 kB main chunk). Parity items
that were checked and are **correct** (do not "fix"): `relTime`, chat caps 16/5 and
timeline 14, absence of chat search/paging/unread markers, `/api/ask`'s real event
shapes, and the gear/Connectors being Clerk-mode-only (`shell.js:536-554` —
`Sidebar.tsx:312` is parity, not a bug).

---

## 2. The plan

Each phase ends in a gate that can fail, states its rollback, and is independently
revertible. Order is deliberate: nothing about the UI can be verified while the
served app 401s, so serving + auth come first; the ask-path correctness work rides
with auth because it is the same code path.

### Phase A — Serve React from the backend, behind a switch (S–M, ~1 day)

**A1. Make the artifact exist and be provably in sync.**
- `ops/build_frontend.sh`: `npm ci && npm run build` in `frontend/`.
- Decide the shipping model (see D-1). Recommendation: **commit `frontend/dist`**
  (remove `frontend/.gitignore:12`) plus a CI step that rebuilds and runs
  `git diff --exit-code -- frontend/dist`, because the app tier has no Node
  (`render.yaml:26`, `ops_stack_up.sh:17`) and a committed bundle is revertible by
  `git revert`. This removes the "silent staleness" objection that would otherwise
  apply to a committed build.
- **Gotcha found while implementing this (2026-10-03):** committing `dist` makes
  Tailwind's automatic content detection scan its own previous output — v4 skips
  `.gitignore`d paths, and `dist` is no longer one. The stylesheet silently grew
  87,515 → 97,530 bytes with utilities harvested from the compiled bundle, and every
  asset hash changed. Fix (applied): pin detection in `index.css` with
  `@import "tailwindcss" source("../src");`. Verified: with the pin, consecutive
  builds are byte-identical and match the committed bundle. Any future build output
  committed to the repo needs the same treatment.

**A2. Serve it with correct cache semantics** (`app.py`).
- Mount **only** `frontend/dist/assets` at `/assets` (never `frontend/`, or `src/`,
  `package.json` and `node_modules` become downloadable) with
  `Cache-Control: public, max-age=31536000, immutable`; do **not** reuse
  `NoCacheStaticFiles` (`app.py:125-138`) for hashed files.
- Serve `frontend/dist/index.html` at `/` with `no-cache, must-revalidate` (the
  `_page()` semantics, `app.py:1820-1821`) so browsers never pin a stale bundle hash.
- Serve `/favicon.svg` and `/icons.svg` from the bundle (they 404 today).
- No SPA fallback is needed: the app has no path routes; it only rewrites query
  params (`App.tsx:182,199,240-241,639`), so every deep link resolves to `/`.
- Keep `/static/**`, `/graph`, `/brains`, `/upload` as they are — they are the
  fallback UI and `LegacyMount` iframes them (`App.tsx:991-995`).

**A3. Make the switch explicit and reversible.**
- `KESTREL_UI=react|legacy` (default `legacy` until A4/Phase B pass, then default
  `react`); document in `.env.example` and `render.yaml`.
- With `KESTREL_UI=react` and no `dist/index.html`, **say so in the log and fail
  visibly** — never silently fall back to legacy.

**A4. Prove it.**
- Gate: `PROVIDER=mock AUTH_MODE=off KESTREL_UI=react python3 app.py` →
  `curl /` contains `id="root"` and `/assets/index-`; every referenced asset returns
  200 (including the favicon); `check_ui_react.py --base http://127.0.0.1:8000` green;
  the parity capture scripts run against **`:8000`**, not only `:5174`.
- Rollback: `KESTREL_UI=legacy` (or revert the commit).

### Phase B — Make the served app authenticated and the ask path honest (M, ~1–1.5 days) — the P0s

**B1. One authenticated transport.**
- `lib/api.ts::apiFetch(path, init)`: awaits Clerk boot once (mirroring
  `static/auth.js`'s `booted` promise), returns `{}` when `authMode !== "clerk"`,
  and otherwise mints a token **per request** via `Clerk.session.getToken()`,
  retrying once with a forced refresh on 401. This is the pattern that already
  exists in `useAuthHeaders` — it is simply not awaited at the call sites.
- Route **every** call through it, including the NDJSON streams (`/api/ask`,
  `/api/brains/<name>/events`). Delete `useAuthHeaders` when nothing uses it, and
  add a dev-time guard (console warning or a small lint/test) for direct `fetch`
  in `src/`, so the invariant survives future work.

**B2. Ask-path hardening** (from §1.3).
- Check `res.ok`/`res.body` before reading, exactly like `static/index.html:1383`,
  and surface the server's `detail` verbatim.
- Per-line `try/catch` around `JSON.parse` (skip the line, do not kill the stream).
- Port the four legacy terminal states: `_(stopped.)_` with partial text,
  "Stopped before any answer arrived.", "No answer returned for that question.",
  and "_(connection lost — showing what arrived.)_" — and stop appending a
  **second** bot turn on error.
- Render failures as the turn's `err` state (`bubble err`, `shell.css:258`), not as
  markdown body text.
- Finalize on `{stage:"done"}` (free the composer, render sources/actions) while
  continuing to consume the citation tail; map only `ev.stage === "step"` into the
  working log (kills the "bypassing retrieval" row, R13).

**B3. Send conversation history** (from §1.4): build the legacy `context` string
from the last 3 turns (`static/index.html:1237-1239`) and pass it on every ask,
respecting `MAX_CONTEXT_CHARS` (`app.py:1187`) — merged with attachment context
when files are present.

**B4. Honest failure states**: no silent empties — `useBrains`, `useChats`,
`fetchChat`, `/api/stats`, `/api/graph` must render 401/403/5xx as a visible state
in the server's own words (the draft box already models this, `App.tsx:809-812`).

**B5. Prove it without a human in the loop.**
- The repo already runs the real app in clerk mode with a signed test identity:
  `auth.inject_jwks_for_test` + RSA JWTs (`tests/test_route_authz.py:12-50`,
  `tests/test_v2_authz.py:20-47`). Extend that into a browser gate,
  `tests/test_react_clerk.py`: boot `app.py` with `AUTH_MODE=clerk`,
  `KESTREL_UI=react` and an injected JWKS; launch Playwright with an
  `add_init_script` stub for `window.Clerk` that returns the test JWT from
  `session.getToken()`; assert brains load, the chat list is populated, an ask
  streams a turn, and **a control run with the stub removed 401s and shows the B4
  state** (so the test cannot pass vacuously).
- Gate: that test green against `:8000`; the no-stub control shows an honest
  "not authorised" state rather than an empty app.
- Rollback: revert; `KESTREL_UI=legacy` still ships the working legacy dashboard.

### Phase C — Close the visible regressions (M, ~1.5–2 days)

Grouped so each item ships with its own screenshot + smoke case. Ordered by user
impact; all are from §1.5/§1.6.

- **C1 Chat surface correctness**: R3 per-turn working logs (store steps on the
  turn), R4 stick-respecting scroll (instant during streaming), R5 real timestamps
  (carry `at` through `fetchChat`/`saveChat`), R6 attachment persistence + render,
  R7 the 8 MB gate and data-URL snapshot, R10 abort the stream on chat switch, R11
  finalize on `done`.
- **C2 Navigation/state**: R1 `popstate` handling, R9 `rememberChat()` parity
  (`?new=1` cleared, `?chat=` written), R8 sidebar list across all brains and on
  every view, R12 brain-switcher filter/sort/confirm.
- **C3 Styling substrate**: add the missing colour roles to `@theme inline`
  (§1.5), then add a guard that fails when a used `bg-*/text-*/border-*` class is
  absent from the emitted CSS. Resolve the `--warn` double definition, drop the
  duplicated `:root`, load Inter or stop claiming it, and fix the undefined
  `--ink`.
- **C4 i18n that actually switches**: R2 — make language React state (context or
  store), derive `greeting()` from `t('greet.*')`, move chip labels inside render,
  translate nav labels and the settings items, fix the corrupted `i18n.ts:556`
  string, and reconcile `LEGACY_TO_REACT_PARITY.md`'s dead `usage.*`/`up.*` keys.
- **C5 Settings / auth / connectors / graph**: R15 anchor the settings pop
  (gear rect) and port Usage + Upgrade modals (CSS and `/api/usage` already exist),
  R16 a covering sign-in gate (mount the Clerk card, keep the theme re-apply),
  R17 Slack/Gmail import + posting (or point `?view=connectors` at the legacy modal
  until they exist — an explicit decision, not a silent one), R14 send `dataset=`
  in `GraphView`/`GraphPage`.
- **C6 Sidebar signature + small polish**: R18 mount `SlideRail` and toggle
  `sb-slide-on`; the P2 list in §1.7 (clipboard fallback, aria-live throttling,
  Escape/backdrop closes, textarea reset, chips→composer, demo label, files-sheet
  note append, `?brain=` forwarding, real `href`s for ⌘-click, `document.title`,
  `crypto.randomUUID` fallback).
- Gate: React smoke (Phase D) covers every C item; desktop 1440 + mobile 390
  captures in both themes under `docs/ui-review/screens/`.

### Phase D — Verification that runs where it matters (M, ~1 day)

- **D1** Rewrite `check_ui_react.py` for the post-port DOM (its docstring is stale;
  the app now *is* `.nav-item`/`#sb-viewmenu`/…), and extend coverage to: intercepted
  NDJSON ask → stream → save → reload-resume; citation chip → source modal →
  `<mark>`; files sheet verdicts + pipeline; draft box (draft → 503 copy); brains
  page (stats + armed delete); composer menus; keyboard (Enter/Shift+Enter/Escape/Tab
  into `.msg-acts`); deep links (`?brain= ?chat= ?new= ?view=`) and Back/Forward.
- **D2** Point it at the **served** app (`--base http://127.0.0.1:8000`, with
  `KESTREL_UI=react` and a static build) and add it to `verify.sh`'s non-quick lane.
  Deal with `check_ui.py` explicitly: it is unrunnable today (§1.1) — either port it
  to the same Playwright-Python harness for the legacy pages or retire it and record
  that the legacy UI is frozen. A dead suite wired into `verify.sh` means a full
  battery can never be green.
- **D3** `detect_frontend.py`: probe `5174` and classify a served React build
  (`/assets/index-…js` + `id="root"`, no `ui.js`) on `:8000`.
- **D4** Turn the parity helpers into gates: `mkdir -p` the output dir, configurable
  URLs, PIL `ImageChops` diff, documented threshold, non-zero exit on drift — React
  served vs the lab legacy twin.
- **D5** CI: declare `playwright` in a CI-only requirements file (absent from
  `requirements.txt`), install a browser, and add `npm run lint`, the React smoke
  against `python app.py`, an assertion that `dist/index.html` and the `/assets/*`
  file it references exist, and (if dist is committed) the A1 staleness diff.
- Gate: the new lane green on a clean checkout, **and** red when deliberately broken
  (remove a `@theme` token, 404 the favicon, drop an auth header) — a gate that
  cannot fail is not a gate.

### Phase E — Cleanup and honest docs (S, ~½ day)

- **E1** Delete the dead components and unused `ui/*` primitives; keep what is
  actually rendered (`Animations.tsx`); fix the 2 lint errors and drive warnings to
  zero or a documented allowlist.
- **E2** Decide the fate of `LegacyMount`/`GraphPage`/`UploadPage` (retire and drop
  `?view=legacy-*`, or surface them in the nav as "full legacy page" and hide the
  React sidebar while mounted) — the current middle state is what the docs
  mis-describe.
- **E3** Reconcile docs: `REACT_UIUX_ADVANCEMENTS.md` §1/§4.1/§4.8/§7 (served
  status, "API calls carry Bearer tokens", usage/upgrade modals, "pixel-diff gates"),
  `vite.config.ts:6-7`'s `/static/app` comment, and mark
  `LEGACY_TO_REACT_PARITY.md` (2026-10-02; most of its ❌ items are now built) as
  superseded with a pointer here.
- **E4** Fold this plan's gates into `EXECUTION_PLAN.md` Phase 9 so "supported
  frontend" has one executable definition of done.

---

## 3. Definition of done (Phase 9's proof gate, made executable)

"React as the supported frontend" is true when, on one machine **and** in CI:

1. `python3 app.py` in the live config shape (`AUTH_MODE=clerk`, `KESTREL_UI=react`)
   serves React at `/`, all referenced assets 200 (favicon included), and every API
   call the UI makes is authenticated — proven by `tests/test_react_clerk.py` with
   and without the token stub.
2. A follow-up question in a fresh browser session is answered **with its referent**
   (B3 verified by the smoke suite), and a 401/500 on `/api/ask` renders as a red
   error state, never as an empty answer.
3. `./verify.sh` runs the React UI smoke against the **served** app and is green,
   alongside the existing 25/25 · 13/13 · 90/90 · 10/10 · 4/4 battery.
4. The Phase 9 walkthrough — create → ingest → ready → ask → cite → open source →
   history survives restart — completes from React alone, with no silent legacy
   redirect.
5. Desktop (1440) and mobile (390) captures are saved as evidence, dark **and** light.
6. `frontend/dist` is provably in sync with `frontend/src`; CI is green (build +
   lint + smoke + served-asset assertions); `KESTREL_UI=legacy` still serves the old
   dashboard as a one-flag rollback.

---

## 4. Owner decisions needed (scope, not correctness)

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D-1 | How the bundle ships | commit `frontend/dist` + staleness gate / npm build step in `render.yaml`+Docker+compose / host the frontend separately | commit + staleness gate (no Node in the app tier today; revertible) |
| D-2 | Graph for beta (EXECUTION_PLAN F6) | finish `GraphView` in React / keep the labeled legacy hand-off / mount the legacy graph page in-app | keep the labeled hand-off for beta (after fixing R14), record it as the honest delta |
| D-3 | FilesSheet `/events` vs `UploadPage` v2 jobs | unify on `/api/brains/v2` + `/api/jobs/{id}` / keep both | unify on v2 — but only after B1, since v2 calls are unauthenticated today |
| D-4 | Connectors for beta | port Slack/Gmail import + posting / point `?view=connectors` at the legacy modal / ship read-only status | port the import/post panels if connectors are in the beta story; otherwise link out explicitly |
| D-5 | Legacy dashboard's fate | keep at `/` under the flag / move to `/legacy` / delete | keep behind `KESTREL_UI=legacy` through beta, then decide |
| D-6 | Inter | load it like marketing / drop the claim | load it, so the polish spec's typography is real |

---

## 5. Order, effort, stop points

```
A1 → A2 → A3 → A4          serve it, flag-controlled, provable            (~1 day)
      ↓
B1 → B2 → B3 → B4 → B5     auth + ask-path correctness (the P0s)          (~1–1.5 days)
      ↓
D1 → D2 → D3 → D4 → D5     make the gates real; CI catches regressions    (~1 day)
      ↓
C1 … C6                    visible regressions, each with evidence        (~1.5–2 days)
      ↓
E1 … E4                    cleanup, decisions recorded, docs reconciled  (~½ day)
```

Stop-and-report points: **A4** (first served React), **B5** (Clerk-mode proof +
ask-path honesty), **D5** (CI green with gates that can fail). C and E are safe to
interleave after B5; C1 (chat-surface correctness) is the highest-value part of C
because it is behaviour users hit on every question.

Total: ~5–6 focused days, i.e. EXECUTION_PLAN Phase 9's 2–4 days plus the three P0
defects that plan did not know about — with the P0s front-loaded, because nothing
else about the frontend is verifiable while it 401s and renders failures as answers.
