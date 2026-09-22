# Bug report — every defect found, with evidence

Audited 22 Sep 2026. Method: read the source, then **verified each finding by execution** — not by
inspection alone. Every claim below has a reproduction or a measured result.

Ordered by severity. Severity is judged by *what it costs the user*, not by how clever the bug is.

---

## CRITICAL

### C1 · Chat history never restores — the feature does not work at all

**The headline feature is broken.** Every page load silently discards the visible conversation.

`CHAT_ID` is generated fresh on each load:

```js
const CHAT_ID = new URLSearchParams(location.search).get('chat')
  || 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
```

`saveHistory()` stores the conversation under that id. On reload there is no `?chat=` in the URL, so
a **new** id is generated, and `loadHistory()` searches for an id that does not exist. It returns
`[]` and nothing is restored.

**Measured:**

| | |
|---|---|
| Stored chat id | `cmuc5bm2bt5wz` |
| `CHAT_ID` after reload | `cmuc5czxxqe32` |
| `idsMatch` | **false** |
| URL query string | *(none)* |
| Turns before reload | 2 |
| **Turns after reload** | **0** |

**Secondary effect:** the orphaned conversations accumulate in `localStorage` forever, one new entry
per reload, until the 30-chat cap silently evicts them.

**Fix direction:** persist the current chat id (sessionStorage or a `?chat=` pushState) and read it
back on load. The sidebar already links with `?chat=<id>` — the ask page simply never writes it.

---

### C2 · Stored XSS in the graph legend — verified exploitable

`static/graph.html:505` interpolates a node **type** straight into `innerHTML`:

```js
.map(([t, c]) =>
  `<div><span class="swatch" style="background:${colorFor(t)}"></span>${t} <b>${c}</b></div>`)
```

Node types arrive from the graph endpoint. For an **uploaded** brain the graph is built by the tenant
from user-supplied documents, so a crafted document is a plausible delivery path.

**Measured:** injecting a node whose type is `<img src=x onerror="window.__pwned=true">` and
re-rendering the legend produced `pwned: true` and an `<img>` in the DOM.

**Same class, lower severity:** `graph.html:525` interpolates `err.message` into `innerHTML` in the
catch handler.

**Fix direction:** build the legend with `createElement` + `textContent`, exactly as `renderDetail()`
already does correctly a few lines away (lines 354–355, 372–378). The correct pattern is already in
the file — it just was not followed here.

---

### C3 · No authentication or authorization anywhere

Every endpoint returns 200 unauthenticated, and **any dataset is readable by name**.

**Measured:**

| Request | Result |
|---|---|
| `GET /api/brains` (no credentials) | **200** |
| `GET /api/stats?dataset=company_brain` | **200** |
| `GET /api/stats?dataset=default_dataset` | **200** — Cognee's internal dataset |
| `GET /api/ask?q=…&dataset=<any>` | accepted |
| `DELETE /api/brains/{name}` | accepted |

`dataset` is a plain query parameter on `/api/ask`, `/api/graph`, `/api/stats` and `/api/source`
with no ownership check. This is the **data-level, not access-level** isolation already recorded in
`IMPROVEMENTS.md` §9.2 — confirmed here by execution rather than by reading.

**Consequence:** for a single-tenant demo it is a trade-off. For anything with two customers it is a
breach. This is the gate on the business case, and it is real.

---

## HIGH

### H1 · Restored answers lose their action row and their suggestions

Even once C1 is fixed, this remains. `renderTurn()` does not call the two renderers:

```js
function renderTurn(role, text, sources) {
  const { turn, bubble } = addTurn(role, text);
  if (role === 'bot') {
    bubble.innerHTML = renderMarkdown(text);
    if (sources && sources.length) renderSources(turn, sources);
  }
  return turn;
}
```

| Renderer | Called by `renderTurn`? |
|---|---|
| `renderMarkdown` | yes |
| `renderSources` | yes |
| `renderAnswerActions` | **no** |
| `renderSuggestions` | **no** |

`restoreHistory()` routes every saved turn through `renderTurn`, so a restored answer shows its text
and its source chips but **no copy/email/steps/chat icons and no follow-up suggestions**. The comment
in `restoreHistory` claims the opposite: *"Prime the action generators … so the buttons work
immediately after a reload."* The buttons do not exist to be primed.

---

### H2 · Documents that failed to ingest are recorded as citation sources

In `create_brain`:

```python
docs, failures = await asyncio.to_thread(documents.extract_many, payload)
...
results   = await asyncio.gather(*(ingest(d) for d in docs))
succeeded = [r for r in results if r["ok"]]
failed    = [r for r in results if not r["ok"]]
...
citations.record_upload(safe, docs)      # <-- ALL extracted, not `succeeded`
```

`record_upload` builds the fingerprint→filename manifest that lets an uploaded brain cite itself.
Passing `docs` records **every extracted document**, including the ones whose ingestion raised.

**Consequence:** a brain can cite a source file that is not in its graph. An answer names a document
the user can open but which contributed nothing — the citation is not merely unhelpful, it is false.
This is the exact failure mode the citation work exists to prevent.

**Fix:** `citations.record_upload(safe, [d for d in docs if d["name"] in {r["name"] for r in succeeded}])`

---

### H3 · A mid-stream cloud failure appends fixture answers to a real answer

`memory_layer.recall`:

```python
try:
    produced = False
    async for event in _cloud(query, dataset):
        produced = True
        yield event
    if produced:
        return
except Exception as exc:
    yield {"type": "chunk", "text": f"(The knowledge graph is unreachable …)"}

async for event in _mock(query, dataset):
    yield event
```

If `_cloud` yields several chunks and **then** raises, the `except` fires, the notice is emitted, and
control falls through to `_mock`. The user sees a **partial real answer followed by a fixture
answer**, concatenated as one response, with only a parenthetical separating them.

The `produced` flag guards only the success path. It does not guard the failure path — which is the
one that matters.

**Fix:** if `produced` is true when the exception fires, re-raise or return; only fall back when
nothing was emitted.

---

### H4 · Unbounded `timeout_s` on the progress stream

```python
@app.get("/api/brains/{name}/events")
async def brain_events(name: str, timeout_s: int = 600):
```

`timeout_s` is a client-controlled query parameter with **no upper bound**.

**Measured:** `GET /api/brains/company_brain/events?timeout_s=99999999` → **200**, connection held
open, polling the tenant every 3 seconds.

**Fix:** clamp to a sane maximum, e.g. `timeout_s = max(10, min(timeout_s, 900))`.

---

### H5 · No length limit on `q` or `context`

`/api/ask` takes both as unbounded query parameters, and `context` is interpolated straight into the
prompt:

```python
question = q if not context else f"{context.strip()}\n\nFollow-up question: {q}"
```

**Measured:** a **10,000-character** question is accepted (no application-level cap). Larger payloads
fail only because of a server URL-length limit, which is not validation — it is an accident of the
transport.

**Consequence:** unbounded prompt size → unbounded token cost on every call, and a trivial way to
inflate someone's inference bill. The client already caps `history` at 3 turns × 700 chars, so the
honest client never gets near this — but the API does not enforce it.

**Fix:** reject `q` over ~2,000 chars and `context` over ~6,000 with a 413, mirroring how
`documents.py` already caps uploads.

---

## MEDIUM

### M1 · `delete_brain` falls back to the raw, unvalidated name

```python
safe = normalize_brain_name(name)
if safe and safe in RESERVED_NAMES:
    raise HTTPException(...)
...
removed = cognee_cloud.delete_dataset(safe or name)
```

`create_brain` **refuses** a name that fails normalization (400). `delete_brain` **passes it
through** to `delete_dataset` whenever `normalize_brain_name` returns falsy. The two routes disagree
about what a valid name is, and delete is the more dangerous of the two.

**Fix:** reject with 400 when `safe` is falsy, exactly as `create_brain` does.

### M2 · `/api/source` ignores `dataset` for corpus files

**Measured:** `GET /api/source?name=05_policy_SLA-credit-01.md&dataset=kestrel_full` returns the
corpus file with `"source": "corpus"`. The file is not checked against the dataset.

For the shared `corpus/` directory this leaks nothing new — every corpus file is already public in
the repo. But the parameter reads as if it scopes the lookup and does not, which is worse than not
having it.

### M3 · Graph: the manual re-centring after clicking a relationship is dead code

```js
if (other) row.addEventListener('click', () => {
  select(other.id);
  cam.x = W / 2 - other.x * cam.k;      // <-- immediately overridden
  cam.y = H / 2 - other.y * cam.k;
});
```

`select()` calls `fitTo()`, which sets `camTarget`. The frame loop's `easeCam()` then lerps `cam`
toward `camTarget` on the next frame, discarding these assignments. The centring appears to work
only because `fitTo` happens to move the camera anyway.

### M4 · TOCTOU on brain creation

`cognee_cloud.exists(safe)` is checked, then ingestion proceeds. Two concurrent requests with the
same new name both pass the check and both ingest. The 409 guard is correct for the sequential case
and racy for the concurrent one.

### M5 · Trailing stream buffer is never flushed

Both stream readers discard `buf` on completion:

```js
while (true) {
  const { value, done } = await reader.read();
  if (done) break;                  // <-- buf is dropped here
  ...
  buf = lines.pop();
}
```

If the final chunk does not end in a newline, the last event is lost. The server does terminate every
event with `\n`, so this is latent rather than active — but a truncated stream would silently drop
the `done` event, leaving the answer as **raw markdown** (the `innerHTML = renderMarkdown(text)` line
never runs) while still being pushed to history.

Affects `static/index.html` (~line 485) and `static/upload.html` (~line 214).

### M6 · `citations._cache.pop()` happens outside the lock

`record_upload` holds `_lock` for the file read/write, then pops the cache after releasing it. A
concurrent `for_dataset` could repopulate the stale entry in between. Small window, small effect —
but the lock is right there.

### M7 · `shell.js` swallows the stats failure entirely

```js
fetch(statsUrl).then(r => r.json()).then(d => { ... }).catch(() => {});
```

An empty catch. If `/api/stats` fails, the sidebar shows nothing at all rather than "unavailable" —
the reader cannot tell a slow fetch from a broken backend.

---

## LOW / worth noting

- **`upload.html:250`** — `finish(false)` runs unconditionally after the try/catch. Correct today
  because the `finished` guard absorbs it, but it reads as if the stream always failed.
- **`graph.html:428`** — `Escape` closes the node inspector. `index.html` binds `Escape` to the
  source modal. No conflict (different pages), but two global `keydown` handlers with the same key
  is a collision waiting for the first shared script.
- **`app.py:270`** — the `start` event reports `dataset or DEMO_DATASET`, which is the *requested*
  dataset, not the one actually used. When the mock refuses an uploaded brain, the stream has already
  announced the wrong one.
- **`documents.MAX_FILES = 40`** while `upload.html` also caps at 40 — the two are independent
  literals with a comment claiming they match. They can drift.

---

## What is genuinely solid

Worth recording, because a bug report that only lists faults is misleading:

- **Path traversal on `/api/source` is properly defended.** Two independent checks — an allow-list
  regex, then `realpath` re-validated inside `corpus/`. All six traversal attempts returned 400.
- **`renderDetail()` uses `textContent` throughout**, so the node inspector is not injectable even
  though the legend next to it is.
- **The upload caps are enforced at the right layer** — count before reading, bytes while reading,
  and PDF/DOCX parsing pushed to a worker thread so `/health` cannot be stalled by a slow parse.
- **`terminal_kind()` distinguishes success from failure**, so a failed ingestion is not reported as
  a working brain.
- **The reserved-name guard exists in two layers** (route and `cognee_cloud.delete_dataset`), so
  neither can be bypassed alone.

---

## Fix order

1. **C1** — chat history is the headline feature and it does not work. Highest user-visible impact.
2. **C2** — XSS. Verified exploitable, and the correct pattern already exists elsewhere in the file.
3. **H2** — false citations undermine the one thing this product is for.
4. **H3** — a mixed real/fixture answer is worse than either alone.
5. **H1** — restored answers lose their controls.
6. **H4, H5** — cheap to fix, close an obvious abuse path.
7. **C3** — not fixable in an afternoon. It is the multi-tenancy project, and it is the gate on
   selling this to more than one customer.
8. M1–M7 as a batch.
