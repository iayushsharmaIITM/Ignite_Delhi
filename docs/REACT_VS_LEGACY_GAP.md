
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
