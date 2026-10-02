# Kestrel Dashboard Parity Report — React (primary) vs Legacy HTML shell

_Date: 2026-10-02 · React commit: `ba8303d`-line + parity commits · Evidence: `docs/ui-review/screens/29–33, 37–40`_

## Premise correction

The new dashboard is **React 19 + Vite + Tailwind v4 + shadcn/ui** (`frontend/`), **not Next.js**. A Next.js rewrite would be the architecture change the standing rules forbid; this report therefore treats "the new dashboard" as the existing React app and brings it to full functional parity with the legacy HTML shell (`static/index.html`, served on :8000) using **the same API endpoints and the same logic**.

## Parity matrix (legacy surface → React)

| Legacy functionality (static/index.html) | API/logic | React status after this pass |
|---|---|---|
| Ask with streaming NDJSON answer | `/api/ask` + stage/chunk/references events | ✅ same endpoint, same event reader (+error turns, +caret) |
| Attachments: texty client-side, binary via `/api/extract`, brain ingest via `/api/brains` append | `/api/extract` + `/api/brains` | ✅ identical contract in `buildContext()` + brain upload (v2 for create; legacy append path intentionally superseded by durable jobs) |
| Source drawer with full document text | `/api/source?name&dataset` (corpus → durable → tenant) | ✅ **wired this pass** — drawer now shows CITED PASSAGE + FULL DOCUMENT with origin label (was excerpt-only) |
| Chat history save/list/open per brain | `/api/chats` + `?chat=` deep links | ✅ server-backed; **deep-link restore added this pass** (`?chat=polish-thread-01` verified live) |
| Brain selector in composer | `/api/brains` list | ✅ **wired this pass** — composer chip is now a dropdown over `/api/brains` (screenshot 39) |
| Brains list + delete | `GET/DELETE /api/brains[/{name}]` (reserved names protected) | ⚠ **partial** — list ✅ (sidebar + selector); delete UI not yet wired (API ready, two-step confirm pattern exists in legacy) |
| Ingestion progress stream | `GET /api/brains/{name}/events` | 🔁 superseded by design — v2 jobs report per-file stages via `/api/jobs/{id}` (CreateBrainDialog); the aggregate `/events` endpoint remains for the legacy path |
| Graph exploration | `/api/graph` + `/api/stats` | ✅ in-app circle view (93/161 verified) + labeled legacy page for full interactivity |
| Work log (pipeline narration) | stage events from `/api/ask` | ✅ stage label in composer (human labels fixed); full log list still legacy-only — minor |
| Draft/send actions | `/api/actions/draft` | ❌ legacy shell ships a draft box; React action row has copy/regenerate only — **deferred** (legacy itself doesn't wire the API either) |
| Connectors + auth | `/api/connectors/*`, Clerk | ✅ Connectors view + themed gate; Slack/Gmail/Drive honestly unconfigured |
| Marketing site | static | ✅ separate surface, done |

## Wired this pass (code)

- `frontend/src/components/SourceDrawer.tsx` (new) — `/api/source` fetch, CITED PASSAGE + FULL DOCUMENT sections, origin label, honest unresolved state, Esc close.
- `frontend/src/App.tsx` — drawer swap; `?chat=` deep-link restore on mount.
- `frontend/src/components/PromptBox.tsx` — composer brain chip → dropdown over `/api/brains` (keyboard-accessible, accent-marked current).
- `frontend/src/App.tsx` — `useBrains()` wired; brain list passed to both composers; CreateBrainDialog refreshes the list on success.

## Verified live (lab stack)

- Deep link `?chat=polish-thread-01` restores the full thread — `screens/37-polish-thread-desktop.png`, `38-final-verification-thread.png`
- Source chip click → drawer: CITED PASSAGE + **FULL DOCUMENT · CORPUS** (full MSA text) — `screens/40-parity-source-drawer.png`
- Composer chip shows ▾ selector — `screens/39-parity-brain-selector.png` (menu verified keyboard-accessible)
- Battery `--quick` green after all changes; live :8000 untouched (Clerk, 1.6.2 candidate).

## Deliberate divergences (not gaps)

1. Brain **creation/ingestion** uses the durable v2 job path (per-file stages, provenance-gated publish) instead of legacy fire-and-forget + `/events` polling.
2. Chat history is server-backed (legacy: localStorage).
3. Graph is a simplified in-app view with a labeled link to the legacy full graph.
4. Actions/draft box: neither frontend wires `/api/actions/draft` today — tracked, not hidden.

## Remaining to reach 100% legacy parity

1. Brain **delete** UI in React (API ready; destructive → two-step confirm like legacy).
2. Draft/send action surface (both frontends need it; API exists).
3. Full interactive graph in React (or accept labeled legacy link permanently).
