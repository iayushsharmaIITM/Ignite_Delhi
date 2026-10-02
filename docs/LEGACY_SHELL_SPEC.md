# Kestrel Legacy HTML Shell — Complete Feature & Style Specification

_Source of truth: `static/index.html` (2,214 lines) + `static/auth.js` (118) +
signed-in captures in `docs/ui-review/screens/29–33`. This documents EVERY
feature, behavior, route, and interaction deployed on the :8000 HTML
dashboard, as the parity target for the React frontend._

## 1. Surfaces & routes (single-page shell)

| View | How reached | Contents |
|---|---|---|
| Chat home | `/` (default) | Sidebar (workspace nav, search, brain-grouped chats), greeting, composer, suggestion chips |
| Thread view | after ask / opening saved chat | Question echo (right), answer (markdown), work steps, source chips, copy/export menus, sticky composer |
| Brains management | sidebar "Brains" | brain list, delete (two-step armed confirm), open |
| Upload / add docs | composer ⋯ → "Add documents…" | files sheet: drop zone, multi-file, per-file rows, pipeline progress (`/api/brains` append + `/events` stream) |
| Graph | sidebar "Graph" | `/api/graph` + `/api/stats` interactive view |
| Auth gate | signed-out, Clerk mode | themed Clerk SignIn mount (`#auth-gate`), i18n title/sub |
| Source modal | citation chip click | `#source-modal`: name, copy button, full text via `/api/source` |
| Account modal | palette / user area | Clerk `openUserProfile` with theme-matched appearance |

## 2. Composer (the core instrument)

- Brain chip → `#brainmenu` popover (brain list, switch in place, `switch-fx`
  spinner overlay animation on switch)
- ⋯ menu (`#menu2`): turn count, Copy transcript, Add documents…, Export
  MD/TXT/DOCX/PDF, sep, Clear conversation (two-step armed confirm → deletes
  this chat from server + storage)
- Attach (`#attach`): file picker → files sheet (`#files-sheet`): drop zone,
  i18n hint (formats + 5MB/40 caps), Add to brain → `POST /api/brains
  append=true` + `/events` pipeline progress streamed into `#pipeline`
- Send (`#go`): streams `/api/ask` NDJSON; stop = abort
- Kbd: Enter send, Shift+Enter newline, autofocus; Escape closes source modal

## 3. Ask pipeline behaviors

- Stage events narrate progress; pipeline narration has measured durations
- Question echo right-aligned; answer renders markdown (headings, lists,
  tables, code, blockquotes, bold)
- Sources → `#source-modal` via citation chips (full text + Copy);
  unresolved → marked, never guessed
- Hedged retrieval (GRAPH → RAG after 8s), router smalltalk bypass,
  attachments → `/api/extract` context + brain ingest (append)
- Work steps with durations; stop button aborts; draft box for composing

## 4. Exports & transcript (client-side, exact logic ported to React ✅)

- `transcript('md'|'txt')` — strips model markdown for txt; includes Sources lines
- `download(name, body, mime)` — Blob + object URL
- Export Word: Word-compatible HTML saved as `.doc`
- Export PDF: hidden iframe, self-printing
- Copy transcript → clipboard with execCommand fallback

## 5. Auth & account (`static/auth.js`)

- Clerk bootstrap shared by every page; mode `off|clerk`; sessions are the
  signed-in truth (prevents gate reload loop)
- `authHeaders()` waits for boot then Bearer token
- Account modal: `Clerk.openUserProfile({ appearance })` — theme-matched
  (light+dark Clerk variable sets)
- Sign out with listener emission; palette shared with the account modal

## 6. Styles & animations (key details)

- Same token family as React (`--bg #1a1a1a`, `--panel #212121`, accent
  `#e8863b`, hairlines, ivory) + light theme via `data-theme`
- `switch-fx`: brain-switch spinner overlay (`.spin.big`)
- `rail`: progress rail under the composer during work
- Sidebar collapse « toggle; `jump-latest` scroll-to-bottom affordance
- Restore overlay for history reload; pulsing pipeline dot; hover reveals on
  action rows; two-step armed destructive confirm styling (`.armed`)

## 7. i18n

16 `data-i18n` strings in the shell + full DICT per language
(en/hi/es/fr/de/zh) ported to React `lib/i18n.ts` — **quoting repaired
2026-10-02** (values had swallowed following keys; sidebar leaked raw keys —
fixed programmatically, verified clean).

## 8. React parity status (post-wiring)

✅ ask/stream, citations→drawer with full document, source-open, chat history
save/list/open/deep-link, brain selector dropdown, attachments+extract+brain
ingest, exports (MD/TXT/DOCX/PDF via ExportMenu), copy transcript, clear
conversation (DELETE chat), brains list, delete brain (BrainsPage, two-step),
graph, auth gate theming, account modal + sign out (SettingsMenu), i18n,
suggestion chips, work log (WorkingLog wired into last bot turn).

⏳ Remaining parity/deltas (deliberate or deferred):
- v2 jobs supersede `/events` aggregate progress (per-file instead)
- Draft box: legacy UI-only; `/api/actions/draft` API exists unwired
- Full interactive graph: React ships simplified view + labeled legacy link
- Command palette: legacy auth.js palette not ported (deferred)

## 9. Verification

Battery `--quick` exit 0 post-parity; thread/drawer/selector/graph verified in
browser against the lab stack (screens 34–40); live :8000 Clerk-gated and
healthy on the 1.6.2 candidate.
