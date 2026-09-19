# RUNBOOK — Ignite Room

Operational companion to `PITCH.md` (which holds the scripts). This file answers "what do I do
at time T", and it exists because the 30 minutes between the rounds is the highest-leverage
window of the day and it is easy to waste.

---

## Timeline

| Time | What | Detail |
|---|---|---|
| **T-60** | Warm everything | `python warmup.py` — all 4 questions, timed. Open `/` and `/graph` in separate tabs so nothing loads cold on stage. |
| **T-15** | Rehearse out loud | Once, start to finish, standing up. |
| **15:30–16:30** | **Mentoring round** | 5-min pitch + 2-min Q&A. Scores the *story*: Problem Clarity · Design Decisions · Scalability · Technical Implementation · Scope & Prioritisation |
| **16:30–17:00** | **THE GAP** | Triage feedback → fix at most ONE thing → re-verify → freeze. See below. |
| **16:50** | **HARD FREEZE** | `python smoke.py` + `python warmup.py`. No changes after this. |
| **17:00–18:00** | **Judging round** | 1-min pitch + 2-min demo + 2-min Q&A. Scores the *product*: Production standards · Technical Understanding · System Architecture · Completeness · Reliability |

---

## The gap: 16:30–17:00

Round 1 feedback is the highest-signal information you will get all day. The trap is trying to
act on all of it and breaking a demo that currently passes everything.

### Step 1 — capture verbatim (5 min)

Write down every comment exactly as said. Do not evaluate, argue, or fix while capturing. You
will misremember the specifics otherwise, and the specifics are what map to points.

### Step 2 — triage (5 min)

Put each item in exactly one bucket:

| Bucket | Test | Action |
|---|---|---|
| **A** | Maps to a round-2 criterion **and** fixable in ≤20 min | Candidate |
| **B** | Fixable, but maps to no criterion | **Skip.** That is polish, not points. |
| **C** | Not fixable in the time | Prepare a spoken answer (Step 4) |

Round-2 criteria, for reference: Production standards · Technical Understanding ·
System Architecture · Completeness · Reliability.

### Step 3 — fix at most ONE thing (15 min)

If more than one item lands in bucket A, pick **one**. Priority order:

1. Anything touching **Reliability** or **Completeness** — you are currently winning both, so
   protect them.
2. Anything that is a *wrong statement in a document* (fastest, zero demo risk).
3. Anything else — probably skip it.

**Why one and not three:** the demo passes 4/4 smoke and all 4 questions today. Every change
risks that. The expected value of a second fix is negative unless it is trivial.

### Step 4 — prepare spoken answers for bucket C (5 min)

Not everything gets fixed. Some things get *answered*. See the table below.

### Step 5 — freeze at 16:50

Re-run both scripts. If either fails, **revert the gap change** — a known-good demo beats an
improved one that broke.

---

## Pre-written answers to likely feedback

Say these out loud once so they are not invented on stage.

**"How is this different from Glean, or just using ChatGPT with my files?"**
> Glean is enterprise-only and RAG retrieves text that *looks* similar. The difference is
> contradiction detection: our graph can tell you two of your own documents disagree. RAG
> structurally cannot — it returns both and hopes you notice.

**"What about permissions? Who can see what?"**
> Deliberately out of scope, and I would rather say that than fake it. Permission mirroring is
> the real enterprise moat and it is 80% of the work in a production system. For three hours we
> spent the time on the memory layer instead. It is the first thing I would build next.

**"Is the graph real, or is it hardcoded?"**
> Real, and you can check: `/api/graph` is served live, and there are data-level endpoints —
> `GET /api/v1/datasets/{id}/data` lists exactly the ten source documents. Want me to run
> `ingest.py` on a new document?

**"How does this scale?"**
> Ingestion scales by adding containers — we proved three documents across three ephemeral
> containers into one shared dataset in six seconds. And because the graph lives outside the
> compute, every container needs exactly **one** credential: an API key. No model key, no
> database password, no volume.

**"What happens if the API goes down mid-demo?"**
> **Offer to demonstrate it.** Point the app at a dead tenant and show it live: `/health` reports
> `cloud · unreachable` honestly, the graph still renders from a committed snapshot, and the ask
> path falls back to fixtures. This is the strongest available answer to a Reliability question,
> because it is a demonstration rather than a claim.

**"Why not Neo4j?"**
> Both keep state outside the container. The tenant instance removes two credentials from the
> critical path — one per container instead of three. At company scale I would move the graph to
> a dedicated Neo4j cluster; Cognee supports it with no application change.

**"What's the business model / who pays?"**
> Honest answer: I would not build this as a general platform — that space is already served
> (Glean at the top, W.Brain at $39/month self-serve, Copilot bundled). The wedge is
> contradiction detection inside one vertical where provenance is the product — due diligence,
> audit, compliance.

**"How long did this take?"**
> Three hours, one builder. And the list of what we deliberately did *not* build is part of the
> deliverable — no connectors, no accounts, no per-user isolation, no billing, no fine-tuning.
> What we *did* build beyond the core is the upload path, so you can create your own brain
> rather than only query ours.

---

## Deploying (when `RENDER_API_KEY` is available)

There is **no `render blueprints deploy`** — a Blueprint deploys by connecting a repo in the
dashboard. The CLI validates and inspects.

```bash
export PATH="$HOME/.workbuddy-ai/bin:$PATH"   # the render CLI is not on PATH by default

# 0. authenticate FIRST. Every command below fails without a workspace:
#    "no workspace specified and no default workspace set"
render login            # device flow via the Render dashboard — you do this, not me
render workspace set    # pick the workspace that will own the services

# 1. validate the blueprint before touching anything
render blueprints validate ./render.yaml

# 2. push, then in the Render dashboard:
#    New -> Blueprint -> connect the GitHub repo -> Render reads render.yaml
#    It creates both services: ignite-web (type: web) and ignite-wf (type: workflow)

# 3. set the two secrets (declared `sync: false` in render.yaml, so Render prompts for them)
#    COGNEE_SERVICE_URL = https://tenant-<uuid>.aws.cognee.ai
#    COGNEE_API_KEY     = <the 64-char hex key>

# 4. verify against the deployed URL
python smoke.py  --base https://<app>.onrender.com
python warmup.py --base https://<app>.onrender.com

# 5. warm it before judging — the first request pays container spin-up
curl -s https://<app>.onrender.com/health
```

**Note on auth:** `render login` is an interactive device flow, so an API key is not strictly
required — you can authenticate yourself. If you would rather hand over `RENDER_API_KEY`, the
CLI reads it from the environment and step 0 becomes unnecessary.

**Do not deploy for the first time during the gap.** A first deploy has moving parts. If it is
not done by 16:30, present locally — the demo is identical and the local path has no cold start.

---

## Failure protocol — two strikes

1. **Strike one:** note it, do not fix it mid-round, keep talking.
2. **Strike two:** `PROVIDER=mock` — the demo completes on committed fixtures.
3. Fix it in the gap, or not at all.

Never debug on stage. The rubric rewards a demo that completes, not one that is technically
perfect.
