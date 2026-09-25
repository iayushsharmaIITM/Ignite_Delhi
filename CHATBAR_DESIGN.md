# CHATBAR — design draft: composer-centric chat for Kestrel

**Status: DRAFT for build.** Merges (a) the composer-centric pattern of
Claude/ChatGPT-class interfaces, (b) the Paper design language, and (c) the
accepted findings of the 25 Sept UI audit. Written to be implemented task by
task; every backend route it needs already exists.

---

## 1 · The research, compressed

How the leaders structure an answer-first chat (Claude.ai, ChatGPT, Grok):

| Pattern | What they do | Transfers to Kestrel? |
|---|---|---|
| **One bar rules all** | A single bottom-anchored composer holds everything actionable: attach (+), context/model picker, send. The canvas holds only the conversation. | Yes — our threadbar (top-right export cluster), chips row, and footer links all collapse into/around the bar. |
| **Context picker lives IN the bar** | Claude: model picker is a dropdown at the composer's left edge; projects are switched from the sidebar, but the active project's name is always visible at top-left. | Yes — brain switcher as a composer dropdown (our `?brain=` machinery is already per-brain everywhere). |
| **Files join from the bar** | "+" opens attach; files ride WITH the message. | Adapted: our "files" are brain documents, not message attachments — the bar gets an *Add to this brain* flow that feeds the existing upload pipeline. |
| **Message actions are hover-revealed, per message** | Copy / retry / edit appear under each response. | Already built (`answer-acts` hover reveal). Keep. |
| **Conversation actions are quiet and out of the canvas** | Share/star sit in a slim header; nothing floats over the transcript. | Export/clear move into a `⋯` overflow menu anchored to the bar; the fixed `#threadbar` is retired. |
| **The send affordance is a state machine** | Send (→) when typed, stop (■) while streaming. | Adopt: one round button, three states (idle/disabled, send, stop). Stop = abort the fetch (AbortController — the reader loop already exists). |

Warm theme stays (Paper). The composer sits on paper like a card, not a black slab.

---

## 2 · The bar, anatomically

```
……………… transcript (only answers live here) ………………

 ⌐─────────────────────────────────────────────────────────────¬
 │ [+ file] [ ▣ Bluepeak brain ▾ ]   ask anything…        (→) │   ← bar row 1
 ⌐─────────────────────────────────────────────────────────────¬
   ⋯ menu · ⤓ export · ⌫ clear        ← bar row 2: quiet text controls,
                                        left-aligned, appear with thread
```

Row 1 — always visible, fixed bottom, Paper card:
- **`[+ file]`** — opens the add-documents sheet (below).
- **`[ ▣ brain-name ▾ ]`** — the brain switcher: current brain + chevron. Demo
  brain shows "◆ Demo brain". Opens a menu listing every brain (name, node
  count) + "＋ New brain…" (routes to /upload and back).
- **input** — borderless inside the card; grows to 4 rows max (then scrolls).
- **`(→)`** — the send/stop state machine (disabled when empty, ■ while streaming).

Row 2 — the conversation menu, rendered only when a thread exists:
- **`⋯`** — overflow: Copy transcript · Export MD/TXT/DOC/PDF · Clear chat
  (the current `#threadbar` cluster, rehomed as menu items).
- **`⤓ export`** — quick MD export (the 90% case) kept one click out of the menu.
- **`⌫ clear`** — behind a two-step confirm (armed state), same as Brains' delete.
- Turn counter ("1 question") lives here as trailing text.

Retired outright: the fixed top-right `#threadbar`, the `CONVERSATION` label,
the footer row on the ask page (graph link already lives in the sidebar;
`/health` link moves out of user view entirely — it stays a route, not a link).

Per-answer controls (copy / email / steps / chat) and follow-up prompts stay
exactly where they are — under each answer, hover-revealed.

---

## 3 · Interaction specs

### 3.1 Brain switcher
- Menu lists `GET /api/brains` results (name, is_demo, node/edge counts when
  the row has them), current one ticked, demo pinned first.
- Switching **mid-conversation** asks: "Start a fresh chat in this brain?" —
  because chats are stored per brain (`kestrel.chats.<brain>`), the honest
  default is navigate to `/?brain=<name>&new=1`. A "keep reading" dismiss does
  nothing. Never merge transcripts across brains silently — that is the one
  way this control could produce a wrong-context answer.
- `?brain=` handling, graph-link scoping, and placeholder swap already exist in
  the page bootstrap — the switcher just navigates.

### 3.2 Add files to the existing chat's brain
- `[+ file]` → sheet (same Paper modal as source-view):
  1. Dropped/chose files are validated client-side with the real rules
     (40 files, 5 MB each, supported extensions incl. code files) — the copy
     on /upload must be corrected to match.
  2. `POST /api/brains` with `name=<current brain>&append=true` — the 409
     guard only fires when append is false, so adding to an existing brain is
     the API's designed path. Demo brain is refused server-side; the sheet
     says so ("the demo brain is read-only — create a brain to add files").
  3. Progress = the existing `/api/brains/{name}/events` NDJSON stream, shown
     as a per-file checklist inside the sheet (states streamed today).
  4. On completion: a toast-in-sheet "2 added · 1 skipped (xlsx)" + a subtle
     "brain updated" chip in the bar; next question answers from the new docs.
- Mock provider: the button explains uploads need `PROVIDER=cloud` (the API
  already returns exactly this message — surface it verbatim).

### 3.3 Send / stop
- Empty input → disabled send. Text → amber-ink send (→). Streaming → stop (■).
- Stop aborts the fetch; the partial answer stays with a "_stopped_" suffix
  (the mid-stream-failure suffix pattern already in `memory_layer`).

### 3.4 Streaming affordance (audit item)
- Replace the three dots with a **streaming caret** — a blinking amber block at
  the end of the streaming text — plus a one-line status above the thread
  ("searching the knowledge graph…"), not under it.

### 3.5 Empty state (audit item)
- When no thread: hero + prompt cards + a one-line graph fact from `/api/stats`
  ("219 nodes · 12 documents · 4 planted contradictions") instead of dead space.

---

## 4 · Control migration map (old → new)

| Today | Becomes |
|---|---|
| `#threadbar` MD/TXT/DOC/PDF/✕ (fixed top-right) | Row-2 menu (`⋯` + quick ⤓) |
| `#turncount` | Row-2 trailing text |
| Footer: "Open the graph view →" | Sidebar only (already there) |
| Footer: `/health` | Removed from the page |
| Starter `.chip` cards | Unchanged (empty state only) |
| `#actions` panel + `.answer-acts` | Unchanged (per-answer) |
| `/upload` page | Still the full-page "New brain" flow; the bar's [+ file] covers add-to-existing |

## 5 · Copy changes (audit P2, folded in)

- Upload page: "40 files max" + "code files (.py, .yaml, …) welcome".
- Brains: "Every brain in this workspace" (no "tenant").
- Bar placeholder stays: "Ask across every document the company has written…".
- Brain menu empty-brain hint: "Files you add here become answerable
  immediately — no restart."

## 6 · Motion (restrained, per audit)

- Bar: 160ms ease on menu open (6px rise + fade); send↔stop crossfade 120ms.
- Turns: 180ms rise+fade entrance; streaming caret blink at 1s.
- Sheet: scale .98→1 + backdrop fade 160ms. All behind the existing
  `prefers-reduced-motion` guard.

## 7 · Implementation plan (ordered, files, acceptance)

| # | Task | Files | Accepts |
|---|---|---|---|
| 1 | `<br>` handling in `inline()`/renderer + cell text | `static/index.html` renderer | no literal `<br>` in cells |
| 2 | Composer rebuild: bar card, row-1 controls, send/stop AbortController | `static/index.html` | bar matches spec; stop aborts mid-stream, partial kept |
| 3 | Row-2 menu (⋯ / ⤓ / ⌫ two-step) replacing `#threadbar` | `static/index.html` | all exports + clear work from menu; battery's UI test clicks them |
| 4 | Brain switcher menu (GET /api/brains; navigate `?brain=&new=1`; confirm-on-switch) | `static/index.html` | switch works from demo→uploaded→demo; per-brain histories intact |
| 5 | Add-files sheet (validation, POST append=true, events stream checklist, toasts) | `static/index.html`, none server-side | adding 1 file to an existing brain visibly updates it; demo-brain refusal surfaced verbatim |
| 6 | Copy fixes (upload 40/code-files, brains workspace, remove /health + footer from ask) | `static/upload.html`, `static/brains.html`, `static/index.html` | no "tenant", no "20 files" |
| 7 | Empty-state fact line from /api/stats | `static/index.html` | shows nodes/docs on demo |
| 8 | Motion pass (caret, turn entrance, sheet, menu) | `static/index.html`, `static/shell.css` | reduced-motion respected |
| 9 | Mobile re-walk of the new bar (390px: wrap, sheet padding, menu hit-areas) | `static/index.html` | no horizontal scroll; bar usable one-handed |
| 10 | Battery + `check_ui` update if control labels changed | `check_ui.py` (SKIP_CLICK list may need "Export" wording review) | full battery green incl. UI 16/16 |

Backend: **no changes required.** `POST /api/brains` (append + 409 semantics),
`GET /api/brains`, `/api/brains/{name}/events`, `/api/stats` all exist.

## 8 · Explicitly out of scope (this pass)

True message-level attachments (files bound to a single question) — our model
is brain-level documents; revisit if "attach to this answer only" becomes a
real request. Dark mode. Multi-model picker (BYOK arrives in Phase 4 — the
bar's left slot is reserved for it then).
