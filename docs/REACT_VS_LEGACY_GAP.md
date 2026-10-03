
---

## PORT PLAN — Path 1 execution (started 2026-10-03)

Foundation laid: `frontend/src/legacy/shell.css` = the legacy stylesheet ported
verbatim (26 KB) and imported globally in `frontend/src/main.tsx`. Build green.

Continuation, in order (each ends in a side-by-side screenshot against :8000):
1. Port the legacy app-shell DOM into `App.tsx` using the SAME ids/classes
   (`#rail`, `.sidebar`, `#thread-wrap`, `.msg`, `.you`, `#composer`, `.chips`,
   `#menu2`, `#files-sheet`, `#source-modal`, `#pipeline`, `switch-fx` …) —
   the CSS already styles them; React only replaces the state layer.
2. Keep every existing React handler (ask stream, extract, brains append,
   chats save/open/delete, exports, auth) bound to the same DOM nodes.
3. Verify side-by-side at 1440/768/390 until indistinguishable.
4. Then re-apply the assistant-ui refinements ON TOP only where they don't
   fight the legacy composition (source chips, focus recipe).

Effort: L (the shell DOM is ~800 lines; handlers already exist in React).
Blocker for final verification: generation routes (unchanged).

### Execution status (2026-10-03, this session)

DONE — Path 1 steps 1–3 complete, verified against the lab stack (:8010,
same DOM/CSS as :8000 without the Clerk gate; :8000 itself is Clerk-gated
signed-out):

- **CSS substrate** (`eb2d585` had laid only half of it): the extracted
  shell.css is index.html's inline `<style>`; `static/shell.css` ("Deck v4",
  linked by every legacy page — sidebar anatomy + the `:root` tokens the
  inline rules consume) was missing. Ported verbatim as
  `frontend/src/legacy/deck.css`; import order in `main.tsx` mirrors :8000's
  cascade (index.css → deck.css → shell.css → bridge.css);
  `bridge.css` = `#root { display:contents }` so React renders the same
  body-level siblings the legacy two-mode layout flexes.
- **Shell DOM** (`f9c6534`): App.tsx renders the :8000 structure —
  `aside.shell` sidebar (brand row, 4 legacy nav items, brain-grouped chats
  with armed deletes + `#sb-viewmenu`, clerk `.sb-user`), `.app-main` with
  `#home` watermark/greeting + `#thread-wrap` turns (`.turn.user/.bot
  .bubble`, `.srcs`, `.msg-acts`, `.working` log with measured per-step
  durations and the engine's own labels via the stageLabel mapping),
  `form#f` bar-card composer (`#brainswitch`/`#brainname`+`#brainmenu`,
  `#menu2` with the legacy item ids, `.atts#pending`, `#q`, `#attach`,
  `#go`), `.chips` with legacy icons, `#rail` ticks + `#rail-tip`,
  `#jump-latest`, `#switch-fx`, `#restore`. Two-mode layout driven by the
  legacy body classes; retract state on the legacy key
  `kestrel.sb.collapsed`. Bot turn + working log open on submit (not on
  first chunk), matching :8000.
- **Source modal** (`#source-modal` port of openSource: origin where-line,
  `<mark>` passage highlight, Copy/Escape) — replaces the tailwind drawer;
  verified pixel-identical against legacy with intercepted identical NDJSON
  streams (generation routes are down; the citation path is stream-shaped,
  not model-dependent).
- **Files sheet** (`#files-sheet` port of openFilesSheet/filesGo/
  streamPipeline: drop zone, 40-file/5MB gates, per-file verdicts, real
  `/api/brains/<name>/events` progress, honest read-only demo notice) —
  replaces the interim "Add documents → legacy-upload" hop.
- **Verification**: side-by-side pixel-diff React(:5174) vs legacy(:8010) at
  1440/768/390 — home/thread/menus/collapsed states ≤ 220 strong-diff px
  (text antialiasing + one i18n capitalization, since fixed); parity scripts
  committed (`parity_shots.py`, `parity_states.py`, channel="chrome").
  `check_ui_react.py` updated to the legacy selectors and green end-to-end
  (it caught one real regression: the chats view/sort pop did not close on
  outside click/Escape — fixed in Sidebar). Battery --quick green after each
  stage. React-only surfaces that intentionally dropped out for parity:
  sidebar chat search, MessageActions email/steps row, PromptBox/
  SuggestionChips wrappers. Connectors moved to the gear menu (as on :8000).

### Completion pass (2026-10-03, same session — post-shell work)

- **LegacyMount retired from the nav**: Brains → `BrainsPage` in-app (the
  two-step brain delete finally reachable; its DeleteButton also had
  `useAuthHeaders()` called inside an async callback — an invalid hook call —
  fixed). Graph → the in-app `GraphView` with its labeled legacy link (the
  spec's deliberate delta), replacing the `confirm()` + hard navigation.
  Legacy pages stay URL-reachable via `?view=legacy-*` as escape hatches.
- **Chat save/resume fixed** (two real regressions vs :8000): `saveChat` only
  ran on the error path — successful asks never persisted; and the legacy
  `sessionStorage` per-brain chat resume was missing. The save runs in a
  streaming-flip effect (a save inside `finally` posts the bot turn before
  its last chunk commits — caught by the intercepted-stream test).
- **Actions/draft surface completed**: the legacy shell styled `#draft` but
  never rendered it and the P6 APIs were unwired. A hover-revealed mail
  action on the last answer drafts via `POST /api/actions/draft` and opens
  the `#draft` box (recipient head, editable body, Copy / Open in mail /
  Send / Close). Send is the approval gate; 503/502 surface the server's own
  words. Happy path needs generation routes (6 Oct) — fails honestly until.
- **Light theme**: home parity holds at light (same noise floor). Fixed
  index.css's light block re-deriving --good/--warn with values legacy never
  uses (legacy light overrides only --bad; good/warn inherit Deck :root).
- **i18n**: the ported shell strings wired to the legacy DICT keys (sidebar,
  view/sort menu, files sheet, `fmt('menu.questions')`). German spot-check
  matches :8010 exactly. The files-sheet notice and pipeline lines stay
  hardcoded — :8000 hardcodes them too.
- **Command palette**: VERIFIED NONEXISTENT — no palette code in auth.js or
  ui.js (grep). The spec §8 "deferred" item is void; the spec's "palette"
  is the settings pop, which is ported. Nothing to build.
- **Open decision (not built)**: FilesSheet uses the legacy `/events`
  pipeline stream; `UploadPage` uses the newer v2-jobs API (per-file
  progress) that the spec says supersedes it. Unifying would be
  frontend-only but deliberately diverges from :8000 — owner's call.
