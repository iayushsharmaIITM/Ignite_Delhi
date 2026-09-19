# Deploying to Vercel

Everything needed is committed. **No tenant is required to browse the app** — the
graphs, the brains list and every page run from the snapshots in `fixtures/brains/`.

---

## What is committed for the deployment

| Path | What it is | Size |
|---|---|---|
| `fixtures/brains/company_brain.json` | Demo brain — 219 nodes / 500 edges | 77 KB |
| `fixtures/brains/kestrel_full.json` | 12-doc brain incl. code artefacts — 233 / 543 | 83 KB |
| `fixtures/brains/acme_industrial.json` | Uploaded brain — 40 / 64 | 11 KB |
| `fixtures/brains/default_dataset.json` | Cognee's internal dataset — 30 / 29 | 6 KB |
| `fixtures/brains/index.json` | Manifest: names, counts, export time | — |
| `fixtures/answers.json` | Committed answers for the demo questions | 4 KB |
| `fixtures/graph.json` | Legacy single-brain snapshot (demo) | 77 KB |

Regenerate at any time with:

```bash
python snapshot.py                 # every brain on the tenant
python snapshot.py --dataset x     # just one
```

Each file is that brain's **own** data. A snapshot is never served for a brain it
does not describe — a fabricated graph looks exactly like a real one.

---

## Deploy

```bash
npm i -g vercel
vercel            # preview
vercel --prod     # production
```

Vercel reads `requirements.txt` automatically and uses `api/index.py` as the ASGI
entrypoint. `vercel.json` rewrites every path to it so FastAPI owns the URLs.

**Environment variables** (Vercel dashboard → Settings → Environment Variables) —
only needed for the live tenant, i.e. for asking *new* questions:

| Key | Value |
|---|---|
| `PROVIDER` | `cloud` (or omit to fall back to snapshots) |
| `COGNEE_SERVICE_URL` | your `https://tenant-….aws.cognee.ai` |
| `COGNEE_API_KEY` | your tenant key |
| `COGNEE_DATASET` | `company_brain` |
| `HOST` | `0.0.0.0` |

Without these, the app runs **fully offline** from the snapshots.

---

## ⚠️ The one real limitation: the ask path will time out on the Hobby plan

**Vercel serverless functions have a request timeout — 10 seconds on Hobby, 60 on
Pro.** `/api/ask` takes **~16–31 seconds** against the live tenant, because the
graph completion runs server-side before the first token.

| Path | Hobby (10s) | Pro (60s) |
|---|---|---|
| `/`, `/graph`, `/brains`, `/upload` | ✅ | ✅ |
| `/api/graph`, `/api/stats`, `/api/brains` | ✅ | ✅ |
| `/api/ask` — new questions | ❌ times out | ✅ (`maxDuration: 60` is set) |

**Options, in order of effort:**

1. **Deploy on Pro** and keep `maxDuration: 60`. Simplest.
2. **Use Vercel only for the browsable app** — pages, graph, brains list all work.
   Demo the ask path locally or on Render.
3. **Put a small always-on host in front of the tenant** (Render web service — the
   repo already has `render.yaml`) and let Vercel proxy to it.
4. **Pre-compute answers.** `fixtures/answers.json` already holds the demo answers;
   the offline path serves those instantly. You could extend it to a wider question
   set, at the cost of only being able to answer questions you anticipated.

---

## Other Vercel notes

- **The filesystem is read-only** except `/tmp`. The upload path writes
  `fixtures/uploads.json`; that write is wrapped so it cannot fail a request, but
  **uploads need `PROVIDER=cloud`** and are better done locally or on Render.
- **Cold starts** add ~1–2s to the first request after idle. Hit the URL once
  before demoing.
- **Streaming** works within the function's time budget; it is the total duration,
  not the streaming, that hits the limit.

---

## Verify a deployment

```bash
BASE=https://your-app.vercel.app

curl -s $BASE/health                                   # ok + provider
curl -s "$BASE/api/brains" | head -c 400               # all four brains
curl -s "$BASE/api/stats?dataset=kestrel_full"         # 233 nodes / 543 edges
curl -s "$BASE/api/graph?dataset=company_brain" | head -c 200
python smoke.py --base $BASE                           # 4/4, but see the timeout note
```

Then open the URL in a browser. `curl` proves the API; it does not prove the page
renders — that distinction has already hidden two bugs in this project.
