
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
