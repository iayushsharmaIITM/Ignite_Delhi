# DEMO_DAY.md — the morning-of runbook (Sept 29)

Everything below was executed and verified on 28 Sept (results in
`AI_RESULTS.md`, ENTRY 1 + the T1 entry). No credentials live in this file —
secrets come from the gitignored `.env`.

---

## 1. Start the stack (in this order)

```bash
# 1. Docker engine (skip if `colima list` shows it running)
colima start

# 2. Brain container + Postgres
docker compose -f compose.oss.yml up -d

# 3. Confirm BOTH healthy before going further (takes ~30s after start)
docker ps --format '{{.Names}} | {{.Status}}'
#    expect:  cognee-oss | Up ... (healthy)     kestrel-db | Up ... (healthy)

# 4. App tier
nohup python3 app.py > /tmp/kestrel_app.log 2>&1 &

# 5. The one check that matters — auth AND upstream must both be good:
curl -s http://127.0.0.1:8000/health
#    expect: "provider":"cloud" ... "upstream":"ready" ... "auth":"ok"
```

If `upstream` is not `ready`, the brain container isn't listening yet — wait
30s and re-run the curl. Do not present until `auth":"ok"`.

## 2. Sign in as the OWNER (Ayush's account)

**If your browser already shows your account (Ayush Sharma, bottom-left of the
sidebar), skip this whole section.** Only a fresh browser needs the recipe.

```bash
# a. mint a sign-in token for the owner user (identifier, not a secret)
source .env
OWNER=user_3JvGjL6x2VWrmAa0IYcvdckHbMv
TOK=$(curl -s -X POST https://api.clerk.com/v1/sign_in_tokens \
  -H "Authorization: Bearer $CLERK_SECRET_KEY" -H "Content-Type: application/json" \
  -d "{\"user_id\": \"$OWNER\", \"expires_in_seconds\": 7200}" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['token'])")
echo "$TOK"
```

In the browser on `http://127.0.0.1:8000` (DevTools console, after the page
and the sign-in card have loaded — sign out of any other account first):

```js
const res = await Clerk.client.signIn.create({ strategy: 'ticket', ticket: '<PASTE TOK>' });
await Clerk.setActive({ session: res.createdSessionId });
// sidebar should now show Ayush Sharma
```

Why this dance: the demo brain is creator-owned — any other account gets 403
on it. That is the isolation working, not a bug.

## 3. Warm up and rehearse (run ~15 min before presenting)

Clerk session JWTs expire every 60s, so warmup reads a token file that a
small loop keeps fresh. Two terminals:

**Terminal A — the refresher (leave running):**
```bash
export PATH="$HOME/.workbuddy-ai/binaries/node/workspace/node_modules/.bin:$PATH"
for i in $(seq 1 80); do
  playwright-cli eval "async () => { const t = await window.Clerk.session.getToken(); return t || ''; }" 2>/dev/null \
  | python3 -c "import sys, re; m=re.search(r'(eyJ[A-Za-z0-9_\-.]{200,})', sys.stdin.read()); open('/tmp/kestrel_token.txt','w').write(m.group(1) if m else '')"
  sleep 15
done
```
(The browser from step 2 must stay open — this reads its live session.)

**Terminal B — the rehearsal:**
```bash
python3 warmup.py --token-file /tmp/kestrel_token.txt
```

**Expected (verified twice on 28 Sept): ALL GREEN, with:**

| Q | Topic | Time | Citations |
|---|---|---|---|
| 1 | renewal-at-risk | 23–25s | 3 |
| 2 | service-credit + approver | **~38–45s (SLOW — known, accepted)** | 3–4 |
| 3 | ownership + RCA | 28–34s | 2 |
| 4 | date consistency | 24–29s | 2 |

Every answer carries citations. Q2 is the "deep question" — present it as
such, or let it finish while you talk.

## 4. Fallback: if the brain tenant is down or misbehaving

The app degrades gracefully to the committed offline fixture — same UI, same
answers from the snapshot graph:

```bash
pkill -f "python3 app.py"
PROVIDER=mock nohup python3 app.py > /tmp/kestrel_app.log 2>&1 &
curl -s http://127.0.0.1:8000/health     # expect "provider":"mock"
```

The fixture (`fixtures/graph.json`, 101 nodes / 173 edges) serves the demo
brain's own data — nothing fabricated. Rehearse this fallback once so the
switch is boring.

## 5. If something is down, the exact recovery

| Symptom | Fix |
|---|---|
| `docker ps` shows nothing / engine error | `colima start`, wait ~60s, then step 1.2 again |
| `cognee-oss` unhealthy or missing | `docker compose -f compose.oss.yml up -d cognee-oss`, wait for `(healthy)` |
| `kestrel-db` unhealthy or missing | `docker compose -f compose.oss.yml up -d kestrel-db` |
| app dead (curl refuses) | `nohup python3 app.py > /tmp/kestrel_app.log 2>&1 &` |
| 403 on questions | you are signed in as the wrong account — redo step 2 |
| 401 during warmup | the refresher (Terminal A) died — restart it, re-run warmup |

## 6. Do NOT touch on demo morning

- Do not create any new brain (single-brain mode; it would pollute the demo
  graph).
- Do not re-ingest, do not delete datasets, do not update dependencies.
- Do not pull/change code after the final warmup — if you must, re-run warmup.

## 7. Verified this morning (28 Sept dry-run)

- `docker ps`: cognee-oss healthy, kestrel-db healthy ✅
- `/health`: provider=cloud, upstream=ready, auth=ok ✅
- warmup ALL GREEN ×2 with the exact timings in §3 ✅
