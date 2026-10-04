## The guard I wrote to kill a blank page was causing one 2026-10-04

The owner's built-in browser showed "Kestrel could not load its interface" while the
server log said the opposite: `index-Df5KrToC.js` **200**, CSS **200**, Clerk handshake
**200**, and the tab title reading "Demo brain" — a title only React sets. The app had
loaded. The guard invented in A-2 to end silent blank pages was producing a loud wrong
one.

The mechanism was a conflation. A `SCRIPT` element fires `error` both when the file is
genuinely gone and when the request is merely **aborted by a navigation** — which is what
Clerk's `?__clerk_handshake=` redirect does on every signed-in load, and what a throttled
embedded webview does to a slow one. The listener called `failed()` on either, and the 4s
empty-`#root` check fired once, in a tab that may simply not have been visible enough to
be given CPU.

The guard now requires evidence before acting: it reads
`PerformanceResourceTiming.responseStatus` and reloads **only** when a bundle request
actually came back 4xx/5xx — never on an abort, and never on an engine that cannot
distinguish the two, because guessing is what caused this. The empty-root check polls to
~10s instead of sampling once, skips entirely while `document.hidden`, and with no 4xx
evidence it explains without reloading rather than spending a retry.

The new gate is "an aborted bundle request does not spend a reload", and it was checked in
the failing direction by restoring the unconditional listener: it writes a retry stamp and
the gate fails. Against the evidence-based guard all four stale-bundle checks pass and the
battery is 13/13, `EXIT=0`.

Worth stating plainly: this is the second time in one day that a defensive mechanism I
added made the owner's experience worse, and both times the fix was to require evidence
before acting rather than to widen the heuristic. A guard that cannot tell a real failure
from an aborted request should stay silent.


## Two corrections and one port 2026-10-04

The owner came back with three things, two of which were about my own work.

**"The animation sticks to the upper left even when hovered on the chat section" was
precise and correct**, and it was a different defect from the retract clock fixed earlier
the same day. The gliding rail matched the wrong element: `.chat-item` is a
`DIV.nav-item` wrapping an `A.chat-link`, `closest(".nav-item, .brain-row, button, a")`
took the **link**, and `row.offsetTop` is relative to whichever element happens to be the
offsetParent — for the link that is the row, not the nav. Measured: hovering chat rows
placed the rail at top=81 while the row sat at 364/442, a 284–362px error, sized 21px
instead of 38px. Nav items and brain rows were pixel-perfect, which is exactly why no
review caught it — the broken case was the one list in the sidebar that is always
populated. Fixed by preferring the outer row and measuring with
`getBoundingClientRect()` against the rail's own containing block, which also drops a
latent `container.scrollTop` double-count. Now 0–1px across 11 nav, 3 brain and 7 chat
rows. The gate asserts each row type with chat **required**, and was checked in the
failing direction by re-injecting the old selector and `offsetTop` maths: it fails on chat
alone, at 285/323/362px — the owner's sentence, turned into numbers.

**"The user section was to be made live and you just completely removed it" was also
right, and it was my scope error.** Asked to make sign-in the only way in, I deleted the
sidebar's whole non-clerk user block. Removing an affordance is a bigger change than
relabelling it, and that one was the door to settings, usage and connectors in every mode.
The row renders everywhere again — signed-in → Clerk profile, signed-out → "Sign in", the
verification seam → "Settings / Language, theme, usage, connectors" pointing at the sheet
that actually works there. What stays deleted is only the "Local mode · No account
required" **label**, which advertised a no-sign-in product path. Strings added to all six
locales, not the two I first assumed existed.

**One port, managed by the thing that already managed one.** I had been running `:8028` as
a preview beside the managed `:8000` all session — two app tiers with different auth modes
and different databases, which is how a preview starts lying about the product.
`ops_stack_up.sh` already brings up exactly one port idempotently; the gap was that nothing
said so. Strays stopped, `:8000` restarted on committed code and verified (new bundle,
account section present, zero page errors), and `verify.sh` now reports any app tier
listening on the known stray ports before it runs. The battery's `:8020` stays on purpose:
it is created and destroyed inside one run, not a service anyone manages.

**Battery:** 13 tiers, 0 failing suites, `EXIT=0`.


## Sign-in becomes the only way in, and the sidebar gets one clock 2026-10-04

The owner's two instructions were "the animation in the side panel is not correct" and
"the only way to the app shall be the sign in, remove the local version". Both turned out
to be bigger than they sounded, and in opposite directions.

**The animation was five motions pretending to be one.** `.shell` animated
`transform .2s ease` while the four offsets that have to move with it — `body`
padding-left, `.app-main` margin-left, `#f` left, `#rail` left — declared no transition
at all. Measured at +50ms: the panel still spanned 0–114px while the content had already
teleported to 0, so they overlapped for ~150ms in both modes. One `--sb-dur`/`--sb-ease`
token now drives all five, verified frame by frame (home mode holds a constant 24px
gutter: 249→273, 158→182, 53→77, 20→44; chat mode keeps `mainLeft == sbRight == fLeft`
on every sampled frame). The gate asserts the resolved `transitionDuration` of each
element rather than sampling frames, because a timing-based gate is a coin flip on a
shared runner — and it was checked in the failing direction by stripping the home rule
out of the built CSS, where it fails on exactly one check and nothing else.

**"Remove the local version" was a fail-open default.** `auth.py:39` returned `off` when
`AUTH_MODE` was unset, so a deploy that simply forgot the variable served every tenant's
chats, brains and graph to anyone who could reach the port — and because `active()` was
`mode() == "clerk"`, any typo (`clerrk`, `none`, `false`) meant the same thing silently.
The UI was honest about it: `Sidebar.tsx` advertised "Local mode · No account required".
Default is now `clerk`, an unrecognised value refuses to start rather than falling
through, and the local-mode block and its two i18n keys are gone. `off` survives purely as
the verification seam that `verify.sh`, both CI jobs and `restore_lab.sh` already name
explicitly — which is why the owner's option choice mattered: deleting it outright would
have taken 13 suites and both CI jobs with it. Measured six directions: unset→clerk,
`clerk`→clerk, `off`→off, `CLERK`→clerk, `none`→RuntimeError, empty→clerk.

Two follow-on effects, both found by asking "what breaks now that the default flipped":
`check_ui_react.py` against a normally-booted app produced ~25 failures that all really
meant one thing, so it now preflights `/api/config` and exits 2 with the command to run
instead; and the startup guard at `app.py:2263` means a clerk-mode boot with no
`CLERK_JWKS_URL` refuses to start rather than serving an app where everything 401s.
`.env.example` gained an authentication section saying all of this, and the two living
docs that described `off` as a product mode were corrected — the historical ones were
left alone, per the doc trust map.

## Contract, focus rings and the blank page: a round that included my own breakage 2026-10-04

This entry has an unusual shape: most of it is recovery from damage I did, and the
parts worth keeping are the two gates that caught it and the three product defects that
only appeared once the gates were honest.

**I deleted 35 route decorators with a regex sweep.** The intent was to extend the error
contract across `app.py`; the script dropped the `i = j; continue` branch that appends
the scanned handler, so every bare `@app.get(...)` line vanished while the functions
under them stayed. `python3 -c "import ast; ast.parse(...)"` passed — a file with no
routes is still syntactically perfect Python. What caught it was `check_ui_react.py`
reporting **25 FAILED: react shell served, composer present, …**, i.e. the browser gate
built last round earning its keep on the first edit that broke the app. Recovered by
restoring `app.py` from `3f011d9` and re-applying the five decorators by hand. The
lesson is written into `ops/api_readiness.py` and `_annotate_common_errors`: anything
that has to touch 39 decorators gets done in schema post-processing instead, where the
worst it can do is misdescribe the contract, which is measurable, rather than delete the
product, which is not.

**The error contract, with codes read out of the handlers.** `POST /api/chats` (400,
401, 403, 404, 409, 410, 413, 422, 503), `GET /api/chats`, `GET`/`DELETE
/api/chats/{chat_id}`, `POST /api/brains`, one shared `ApiError` schema, `500` on all 39
operations and `401` on the 31 `/api/*` routes that actually gate. Two claims died in
the checking: `403` is **not** on `POST /api/brains` (nothing there raises it — my draft
list said it was), and `404` **is** on `POST /api/chats` (the ownership error), which the
draft omitted. Codes that mean different things on different routes take a per-route
`notes=` description, because a shared 409 about chat trimming would be a lie on brain
creation.

**A 500 the client could not read.** Starlette answers an unhandled crash as plain text
`Internal Server Error`, while `frontend/src/lib/api.ts:111` parses failures with
`res.json().catch(() => null)` — so the one error class with no `detail` was the one the
user most needed a sentence for. Now `@app.exception_handler(Exception)` logs the
traceback and returns `{detail}`; `HTTPException` still reaches FastAPI's handler first,
so the deliberate 409/410/413/503 bodies are untouched. Verified through the ASGI app:
`500`, `application/json`, traceback in the log.

**The owner's blank page, reproduced from the server's own log.** Live `:8000` rendered
nothing, and the reason was in `/tmp/kestrel_app.log`: three 404s for
`index-SSCQYO2q.js`, `index-m876h3li.css`, `Markdown-anNGsjxq.js` — the hashes the
*previous* build shipped, which `ops/build_frontend.sh` had just deleted. `/` already
sends `no-cache, must-revalidate`, so this is not a header bug; a tab restored from
bfcache still asks for the files it was handed. `frontend/index.html` now reloads once
on a failed chunk and, if that does not fix it, shows a `role="alert"` panel with a
Reload button instead of a dark empty screen. Gated by a `stale bundle` section that 404s
`/assets/index-*.js` and asserts the message appears; healthy loads measured one
navigation, no loop, flag cleared.

**Three false accusations, all mine, all caught before they were committed.** (1) A
"`--accent`/`--focus` token collision" — I had sampled the ring at 0ms, mid-transition;
settled, it is exactly `2px solid rgb(180,83,9)`, which is what `DESIGN.md:46` asks for.
(2) "Six controls have no focus indicator" — asserted on `outlineStyle` alone, and those
controls draw their ring with `box-shadow`, which is how this sheet works. (3) "19 raw
hex literals violate rule 1" — 16 of them are Clerk `appearance.variables`, which must be
literal; migrating them would break sign-in, not fix it. The corrected focus gate is now
checked **in the failing direction**: injecting `:focus-visible{outline:none!important;
box-shadow:none!important}` drops it to 0 of 12, and as shipped it passes 11 of 11.

**What the corrected gate then found for real:** `#rail .tick.here` carries a resting
glow at specificity 1-2-0 that outranks the global `:focus-visible` rule, so tabbing to
a rail tick changed nothing on screen — a WCAG 2.4.7 failure on a control no one had
ever tabbed to. Fixed with an explicit `#rail .tick:focus-visible` outline.

**The readiness number, re-derived rather than re-asserted.** `ops/api_readiness.py` is
committed; the earlier `/tmp` version had hardcoded verdicts, which is why the score had
been moving by amounts nobody could attribute. Same scorer, same 45 checks: **56.6%**
with the error contract ablated, **59.7%** with it. Not agent-ready — the bar is ≥70% and
zero criticals, and E1 still fails. Last round's doc estimated this work at "+8 to +10
points and it clears the only critical"; the measured answer was **+3.1 and it cleared
nothing**, because E1 is one binary and the real gap is now P1: 0 of 39 success responses
carry a schema. An intermediate pass that rewrote `operationId` measured zero gain
(FastAPI already emits 39 unique, method-qualified ids) and lost information, so it was
reverted rather than kept because it looked like work.

**CI ran for the first time, on the 175th commit, and immediately out-voted every local
green.** `24a2308..6e96fb6` pushed to `main`; run `37168535441` failed **both** jobs at
`pip install -r requirements.txt`, and the reason was in the file the whole time:
`fastapi==0.141.1` requires `starlette>=0.46` while line 10 pinned
`starlette>=0.37.2,<0.39.0` — an unsatisfiable set, so a clean install could never have
worked. Six more pins had drifted identically (`uvicorn`, `requests`, `python-dotenv`,
`python-multipart`, `pypdf`, `cryptography` all declared versions no machine here has
ever installed). Corrected to what live actually runs — measured from the running
process: `fastapi 0.115.0` + `starlette 0.38.6` — and verified by resolving the whole
file from scratch (`pip install --dry-run --ignore-installed` → 59 packages, exit 0)
rather than by asserting it looks right now. This is exactly the M-delivery.1 bet: the
dependency file had been validated only by inherited local state.

**The second run got further and taught a harder lesson.** Install passed, the fresh-schema
bootstrap passed on the hosted runner, and **the whole browser suite passed on Linux** —
then `[documents]`, `[connectors]` and the chat-integrity step failed for three
independent reasons that all say the same thing:

- `test_documents.py` made its PDF with `/usr/sbin/cupsfilter`, which is macOS-only.
- `test_chat_integrity.py` SELECTed an org that already had access to `company_brain`, so
  on CI's empty Postgres it died on `None["org_id"]` before asserting anything.
- `connectors_test.py` inherited `CONNECTOR_VAULT_KEY` from my `.env`; without it the
  vault refuses and OAuth start answers 503 **by design**, so the test's own expectation
  of 302 was the bug.

So "13/13 green" had been a statement about one Mac, not about the product. Each fix was
reproduced before it was made — an empty database created on the lab *server* (not the
lab's populated `kestrel`) for the first two, and a symlinked copy of the repo **without**
`.env` for the third, which failed locally with CI's exact 503 — and each was then verified
in both directions. All three suites exit 0 on an empty database, `connectors` is 90/90 with
and without a `.env`, and the scratch database and copy are gone with 0 `itest` rows left.

**And the battery could not have told me any of that.** It printed `FAIL — see
/tmp/kestrel_verify_docs.log`, a file that exists only on the runner, so the diagnosis
started by reading source and guessing. `note()` now tails the log inline; self-tested in
three directions (FAIL with a log prints it, PASS prints nothing, FAIL with a missing log
degrades instead of crashing the battery).

**The third CI run found the one thing I should have found first.** With the inline tails
in place, `[connectors]` reported its own reason immediately — and following it led to a
**data-loss hazard**: `connectors_test.py` deletes `connector_credentials` rows for
`OWNER = "|"`, which is the key a single-user install stores its *own* connected accounts
under, and it resolved `storage.DATABASE_URL` with no guard — standalone that is
`storage.py:37`'s hardcoded default, **`localhost:5433`, live**. The live tier already has
the table this suite creates, so it has been running there. The live vault held **0 rows**:
nothing was destroyed, and that is luck rather than a control. The suite now refuses any
database that is not the lab port (verified — run with no `DATABASE_URL` it prints
`REFUSED: … localhost:5433/kestrel` and exits 2), the battery treats it as lab-only, and
CI's `ui` job runs it so the vault/OAuth contract is exercised on a hosted runner rather
than only on a Mac. The underlying default — a live connection string with its password in
source, which the live app currently depends on because `.env` sets no `DATABASE_URL` — is
recorded as **A-14** and left open: guarding it changes boot behaviour for `:8000`, so it
is the owner's call, not a thing to slip in while fixing CI.

**CI is green on the hosted runner: run `37169797906` at `75901ac`, `fast` 13/13 steps,
`ui` 17 passed + 1 skipped.** That is the first run this repository has ever had that
finished, and it took four pushes to get there — unsatisfiable pins, a macOS-only test
fixture, two suites that assumed seeded database state, and the live-DB hazard behind the
last one. `BLOCKERS.md` M-delivery.1 is partly closed: `ci.yml` stopped being "a well-formed
intention" and became a control, by failing on a machine with no inherited state. Still open
there: no required check or branch protection, so a red run blocks nothing, and the off-disk
copy. Still open in the contract: P1 success schemas, E3 error codes, PF1 rate-limit headers,
and **A-14** — `storage.py:37`'s hardcoded live connection string, which the live app
currently depends on because `.env` sets no `DATABASE_URL`.

**Postman collection shipped without the MCP** (`docs/api-analysis/kestrel.postman_collection.json`,
39 requests from the served document, bearer auth on a variable, every request asserting the
status codes the contract documents). Generating it produced a finding the readiness analysis
had missed: **10 of 12 POST operations declare no `requestBody` at all** — only `/api/brains`
and `/api/brains/v2` do, because those are the two using `Form`/`UploadFile`; the rest call
`await request.json()` by hand, so FastAPI has nothing to generate from.

**The preview then caught my own fix being wrong.** Opening `:8000` for the owner produced
the panel in the screenshot above — and the server log had **zero asset 404s**, so nothing
was missing. The stale-bundle guard's retry allowance was a once-per-session flag: the tab
had failed during the ~3s restart window, burned its single reload, and stayed pinned on
"could not load its interface" over a healthy server. A fix for "never render a silent
blank page" that can pin a loud wrong page forever is not much of a fix. It is now a
timestamp with a 20s cooldown, and the Reload button clears it so a deliberate click always
retries from scratch. Both new gates were checked in the failing direction by re-injecting
the old flag logic into the served file — they fail against it and pass against the new
guard. Live needed no restart: `index.html` is read from disk per request, so the
corrected guard was serving the moment the build landed.

**Final state, measured:** `./verify.sh` → 13 tiers, 0 failing suites, `EXIT=0`. Live
`:8000` restarted on the committed build and checked in a browser (new hashes
`index-of6ZiLeY.js`, recovery script present, 15 mounted nodes, composer + 4 chips, zero
page errors) and over HTTP: its `/openapi.json` scores identically to the committed one
(59.7%), and the data paths fail closed exactly as documented — unauthenticated and
bogus-token requests to `/api/chats` and `/api/ask` both answer
`401 {"detail":"A valid Clerk session token is required."}`.

## Structure pass: dead code out, document map in, and a scanner that sees ignored files 2026-10-04



Three installed capabilities were added by the owner for this pass — Better Harness's
`init` aside, that meant the Postman MCP connector, the CodeRabbit CLI and graphviz.
Two are usable, one is not yet, and the interesting result was not from any of them.

**Installed and used.** `graphviz 16.1.0` rendered `docs/architecture/deployment-topology.{svg,png}`
from the `.dot` source, and generated renders are now gitignored so the canonical text
sources stay reviewable. `coderabbit 0.8.2` came from the official Homebrew **cask** —
the npm name `coderabbit` is a `0.0.1-security.1` placeholder, i.e. a squat, so
`npm i -g coderabbit` would have been the wrong install; the CLI is signed out and
`coderabbit auth login` is interactive, so the review it enables is still the owner's.
The Postman MCP installed and reports `runtimeReady`, but its tools are not in this
session's catalog yet — it needs a reload, so the hosted readiness analyzer is still
unverified and the local 48-check score stands.

**Dead code removed on evidence, not on vibes.** An import/invocation scan (not the
filename grep that initially lied to me and had to be redone) found four root modules
with zero importers and zero invokers: `battery.py` (superseded by `verify.sh`),
`contract_test.py`, `provider_check.py`, `slack_scopes_test.py`, plus
`STACK_AUDIT_PROMPT.md`, a one-time prompt whose output already exists. 880 lines out;
`./verify.sh` re-run afterwards → exit 0, 0 failing suites, so nothing depended on them.

**`docs/INDEX.md`** now classifies all 32 root documents as living / historical /
business, with inbound-reference counts and last-touch dates, and lists five clutter
items deliberately left alone because removing them is a decision, not a finding:
the unwired `parity_*` trio, two screenshot trees (3.1 MB of it referenced by
`README.md`), the one-time v1.6.2 cutover kit, three near-duplicate doc pairs, and the
owner's untracked files.

**The scanner found what our own gate structurally cannot.** `secrun scan --all` looks
at ignored files; `ops/check_secrets.sh --all` scans tracked files only. On that first
look: a real `AKIA…` AWS access-key id in `var/backups/20261003T211935Z/env.app`,
one of 8 plaintext copies of `.env`/`.env.oss` that `ops/backup.sh` takes on purpose
with `0600` (verified), sitting on the same disk as the data they restore and inside
the `~/Desktop` path that iCloud and TCC both reach. Nothing is in git — `var/` is
ignored, and all 12 tracked-file hits are false positives, including a minified React
warning and the detector's own regex text; `--env` and `--context` came back clean.
Recorded as **M-sec.1** with rotation as the owner's call, because a key that has sat
in plaintext copies needs rotating at the provider, not deleting on disk.

**One self-capture worth the space.** My own edit that inserted `M-delivery.1` consumed
the `M-ops.1` heading and orphaned its body — the third time this session an edit to a
markdown file ate a neighbour. `M-ops.1` is restored and the file's six headings are
verified in order. The later `M-sec.1` insert was checked with `grep -c` before being
believed, because the first attempt silently did nothing and my script still printed
success.

## The harness itself got reviewed, and it failed three ways 2026-10-04

Ran the installed plugin set over the project in dependency order — Better Harness
(three independent read-only evidence passes + lead reconciliation), then
`better-harness:init` for the missing entrypoint, then architecture, API, and UI
passes. Full defect ledger: BUGS_AUDIT **Round 4**; rendered report:
`.qoder/better-harness-runs/2026-10-04-full/report.canvas.tsx`.

**What it found that we had not.** The project had no agent entrypoint at all
(`entrypoints: 0` in the asset inventory), and the document agents were actually
routed through — `CLAUDE_CONTEXT.md` — told them to verify with `pytest`, which
`verify.sh` itself says collects 2 of 13 checks. So the instruction surface could
produce a false green on request. Separately, the two suites that guard history loss
and the creation race were unreachable from any automated path, and a third file
(`test_auth_isolation.py`) had **no runner**: running it printed nothing and exited 0,
and because it creates and truncates a database on whatever `DATABASE_URL` names, its
documented invocation was writing to the **live** server by default. `commit.sh`'s
`git add -A` was one routine commit away from putting the review's own evidence lanes
into history.

**Fixed with measurements, not intentions.** `AGENTS.md` created from repository
evidence only (every command re-run before being written down); `ops/doc_health.sh`
added and wired into the battery as the `doc-health` tier — and proved to have teeth by
temporarily removing `AGENTS.md` (exit 1) and restoring it (exit 0); the isolation
suite given a real runner (5/5 under both `python3` and `pytest`) plus a
lab-only refusal (a 5433 URL now exits 1 with the reason); `chat-integrity` and
`brain-claim` added to the CI job that already provisions Postgres on 5434 (its red/green
effect is only observable after a push, which is the owner's call); `.qoder/` ignored,
confirmed by `git status`; and `POST /api/chats`'s full chain documented with
line-level citations (`docs/api-analysis/post-api-chats.md`).

**Two findings I want on record about my own method.** First, verifying the repair
route for the isolation suite is what revealed it was pytest-only — had I implemented
the review's suggestion literally, I would have added a **vacuous gate that always
passes**, the exact defect class this project has now been asked to hunt twice.
Second, while checking whether the CI wiring needed a dependency I found
`requirements-dev.txt` does not contain `pytest` at all, so that suite cannot be added
to CI without the owner approving a new dev dependency; it is documented rather than
smuggled in.

**One incident, stated plainly.** While probing prerequisites I ran
`python3 test_auth_isolation.py` with the ambient `.env`, which pointed it at the live
Postgres container. It ran `TRUNCATE` on four tables inside that server's pre-existing
`kestrel_test_auth` database (created 28 Sep by an earlier invocation, 0 rows before
and after — verified). **No application table was read or written**: the app's data
lives in `kestrel`, which was untouched. That incidental write is what the refusal
guard above exists to prevent, and it is the reason the guard is the fix rather than a
note in the docs.

**Artefacts added.** `AGENTS.md`; `ops/doc_health.sh`;
`docs/architecture/{deployment-topology.md,.dot,.mmd,doc-health.md}`;
`docs/api-analysis/{post-api-chats.md,agent-readiness.md}`;
`docs/ui-review/UX-AUDIT-2026-10-04.md`.

**Measured, and honestly bounded.** The API's agent-readiness score went 50.0% →
57.6% after declaring the bearer scheme, servers and description (it stays "Needs
Work": one Critical check — typed error/response schemas — is still failing, and
adding `response_model` would *filter* fields the React client reads, so it is
documented as a deliberate next step, not a quick win). CodeRabbit could not run: the
CLI is not installed and installing it is the owner's call — the independent-review
function it would have served was covered by the three read-only evidence passes
instead. The UI audit produced six findings, including a focus-ring gap and 18 raw hex
literals in components that `DESIGN.md` forbids; two of its first-pass numbers were
thrown away after re-measurement (a "20 contrast failures" artifact of comparing text
against transparent backgrounds, and a focus check that used scripted instead of real
`Tab` focus).

Battery after all of it: `./verify.sh` exit 0 with the new `doc-health` and
`auth-isolation` tiers; `./verify.sh --quick` (the CI lane) also green.

## Two reviewers read the work cold, and both were right 2026-10-04

The previous entry's evidence was largely real, but a fair amount of it was
*asserted by the same process it was certifying* — receipts written by the script
being tested, suite labels typed by hand, docstrings describing intent. So two
reviewer subagents read `60f87a1..0c33739` (37 files, +2761) cold and read-only,
with no session history. Both returned "not ready". Every finding below was then
re-measured by hand before being accepted; none was rejected. Full detail is
BUGS_AUDIT **Round 3**; the operational consequences are BLOCKERS **M-ops.1/2**.

**What was actually broken, and how it was proven.**

- The secret detector blocked its own repo, so CI was red on every push. Measured:
  `--all` exit 1, one hit, on the line that exists to self-test the pattern.
- The nightly backup overwrote its own FAIL receipt with OK — and chasing it found
  three more: only one of two tars verified, a dump check pg_dump 17 can never
  pass, and a **stale installed copy** writing runner chatter into every dump.
  Verified by forcing failures, by kicking the job through launchd, by checksums,
  and by restoring that artefact into the lab.
- CH-8's "single snapshot" was false (READ COMMITTED snapshots per statement, and
  `psycopg` 3.2.3 has no `transaction(isolation_level=...)`), while its test asserted
  only `hasattr`. Now a FOR SHARE lock plus a race test that carries its own
  control: the unlocked read must tear, or the suite prints that its own
  assertion proves nothing.
- **"Create a brain" was a dead button on live.** The dialog posted to
  `/api/brains/v2`, which 404s unless `KESTREL_JOBS_V2=1` — set nowhere outside
  its own test. Confirmed against the running process. The server now publishes the
  capability (`/api/config → brainCreateV2`) and the client asks before choosing a
  route; `smoke.py` compares the claim with the route's behaviour and
  `check_ui_react.py` drives the dialog end to end.
- Migrations 0002/0005 collided with `storage.init()` and disagreed on the type of
  `chats.brain_id`, so a database's shape depended on how it was born; the release
  phase (migrate before first boot) died on `relation "chats" does not exist`. Both
  orders now run from empty to `0006 (head)` on scratch databases, which were then
  dropped.
- Rate-limited and oversize uploads leaked their brain-name claim; `mark_brain_ready`
  could flip any row by name; a storage outage was served as an empty chat history;
  and the CH-1/CH-2 guards were SELECT-then-write with no lock.
- `verify.sh` started its mock tier on **port 8000 — the live app's port** — and its
  guard was to abort if anything held it, so the battery could not run while the
  demo was up. The app tier now runs on `:8020`, refuses an occupied port, and
  asserts `provider: mock` from `/health` before trusting it.

**One more, found while writing the gate for the gate.** The UI suite switches the
interface to German in its settings section and never restores it, and every
downstream locator written in English therefore matched nothing — inside
`if locator.count():` guards, which "pass" by never running. The create-brain gate
would have joined them. The brains section now pins the locale, re-navigates to the
view it is testing (opening the files sheet from a row had been quietly taking it
to the chat view), and reports a missing affordance as a FAIL instead of a skip.
That revived a delete-arming check that has been skipping since it was written.

**Battery, after all of it:** `./verify.sh` → 0 failing suites, exit 0, on the new
port; smoke now 5/5 with the capability check; chat-integrity with the CH-8 race
test and its control; ui-react with the create-brain flow actually executed.

**Not claimed.** Live *answering* is still unmeasured from here — `/api/ask` is
Clerk-gated, so a CLI probe gets 401 and never reaches the brain; one question in
the browser settles it, and the lab's provider quota (exhausted until 2026-10-06
07:29 UTC) makes it worth asking before a demo. The two older nightly dumps are
known-corrupt and were left on disk rather than deleted. And CI has still never run
this battery on a machine that is not this laptop: `--quick` is all CI executes,
while the browser and lab-DB suites are local.

## Ops that have to be true without anyone checking 2026-10-04

Three gaps that only matter on the day they matter, each closed with a check that
proves itself rather than a claim.

**Secrets.** `commit.sh` runs `git add -A`, so a pasted key reaches history on an
ordinary "wip" commit. `ops/check_secrets.sh` scans the stage area before every
commit and every tracked file in CI. It **self-tests**: if the pattern cannot match
its own example the script exits 2 instead of reporting "clean", because a silently
broken detector is the worst of the three outcomes.

*(Corrected the same day by the Round 3 review: that paragraph then claimed "the
tracked repo scans clean today", and it was false. The self-test literal matched
the very pattern it was proving, `--all` scans every tracked file including that
script, so `ops/check_secrets.sh --all` exited 1 and CI failed on every push. The
probe is built at runtime now, and the guard was re-measured in all three
directions: repo-wide scan exit 0 over 314 tracked files, planted key exit 1,
sabotaged pattern exit 2 — so the fix is not a disabled detector. A planted key is
still caught in a normal source file *and* inside `.env.example`: templates are
exempt from the filename rule on purpose, never from the content rule.)*

**Backups.** They existed as a script and a hope. Installing a schedule exposed
BLOCKERS **M-ops.1**: launchd cannot read `~/Desktop` at all (exit 126, `Operation
not permitted`), so the login "self-healing" job has never run — which is why four
colima stops left the stack down while a log written by a *terminal*-launched run
made it look alive. The nightly backup therefore lives outside the repo
(`~/Library/Application Support/Kestrel/…` → `~/Kestrel_backups`), reads nothing
under Desktop, and was verified **through launchd**, not a shell: last exit 0, 12 MB
dump + both volume tars + SHA256SUMS. Artifacts are checked, not assumed — `tar tf`
and a requirement that the dump END with pg_dump's own terminator, which is exactly
what caught one of my own status echoes being written *into* `db.sql`. The receipt
answers "when did this last work" (`--status` → OK / FAIL / STALE, exit 1 past 36h,
tested against a 92 h receipt): a stale "OK" and a broken job otherwise look
identical. `ops/install_agents.sh` installs it; no plist with a repo path is
committed, because that installs a job guaranteed to fail. The stack watchdog needs
the repo, so it is reported with three concrete remedies rather than rewritten
silently.

*(Corrected the same day by the Round 3 review, and this one was serious. Two of
the claims above were produced by a script that could not tell the truth:*

- *`run()` wrote `FAIL` and then `return`ed, with no `set -e`, so the script fell
  through to the line that writes `OK`. Every failed nightly reported success.*
- *"status goes to stderr so it cannot pollute a dump" was true of the **repo**
  copy only. The copy launchd actually runs had been installed from an older
  revision that echoed to **stdout** — into the `> db.sql` redirect. Both dumps on
  disk end with a literal `  ok: pg_dump`, i.e. a syntax error waiting on the day a
  restore is attempted. The launchd log proves it: the 03:17 run records
  `ok: state-volume`, `ok: data-volume`, `ok: verify-dump` — and no `ok: pg_dump`,
  because that line went into the dump instead of the log.*
- *`verify-archives` listed only the state tar, and `verify-dump`'s `tail -3` can
  never match pg_dump 17, which writes `\unrestrict <token>` after its terminator.
  So the dump check failed every night and had its FAIL receipt overwritten.*

*All four are fixed and re-measured: forced failure leaves `FAIL` and exit 1; each
artefact is checked for existence, non-emptiness and listability; the dump verifier
accepts a good dump and rejects both a truncated one and the actual polluted
production file; `install_agents.sh --verify` hashes repo against installed and
exits 1 on drift (it said DRIFT before the reinstall). The job was then run
**through launchd** again and produced a clean, checksum-verified artefact, which is
the one `ops/restore_lab.sh` has since restored successfully.)*

**Restore.** The drill had two latent bugs and could not have told anyone: it
restored onto an un-cleared schema (`relation "alembic_version" already exists`),
and every failure after that died under `set -e` with no output — including one of
my own first attempts, where `set -e` aborted on the `curl` line before the error
report I had just added could run. Now: schema dropped first, status goes to stderr
so it cannot pollute a dump, a 240 s ask ceiling with the timeout reported as
itself, an `EXIT` trap so a failed drill leaves no orphaned server on `:8010`, and
a verdict line with a real exit code.

Honest scope of what is proven: the data layer restores and is queried
(`brain_access=2`, `chats=8`, `graph_node=93`, dataset present, lab cognee healthy).
The final "ask the restored brain" gate **FAILS** (`0 chars, 0 refs`) because the
lab cognee has no working LLM endpoint (`LiteLLM TimeoutError` in its logs) —
recorded as BLOCKERS **M-ops.2**. So "we can restore" is proven for data and
explicitly unproven for answering, and the drill now says so on its own.

*(Corrected the same day, twice. The cause is not a timeout: the lab's credential
is out of its provider's free allowance — `RateLimitError … next rolling 7-day
period starts on 6 Oct 2026 at 07:29 UTC` — and cognee's retries burn the 240 s
window. That is an upstream quota, not lab config, and it expires on its own. And
"the data layer restores" now covers the artefacts the **schedule** produces:
`restore_lab.sh` only understood `ops/backup.sh`'s `.tgz` names and repo-relative
paths, so the nightly `.tar` sets in `~/Kestrel_backups` had never been fed to it.
Both nametypes and absolute paths work now, and the first nightly artefact ever
drilled restored schema, rows, both volumes and the dataset.)*

## M4 closed — a brain name is claimed, not probed 2026-10-04

The one defect the 22 Sep pass deliberately left open because it needed a design
decision rather than a patch. `cognee_cloud.exists(name)` reports only the past,
so two concurrent `POST /api/brains` with the same new name both heard "does not
exist", both ingested, and the ownership row then credited the finished dataset
to whichever writer inserted first: the loser's documents sat inside a brain it
could no longer reach, and nothing in the log was wrong. A lock was the wrong
shape too — an upload runs for minutes and a crashed process takes its lock with
it.

The rule now: claim the name with an atomic `INSERT … ON CONFLICT DO NOTHING`
(`status='creating'`) **before** any work, flip it to `'ready'` only when the
dataset is confirmed. A concurrent create gets 409. The creator may re-enter its
own claim instantly, so a failed upload never locks its author; another identity
may retake a claim only after 15 minutes and only while the dataset still does
not exist, which means that create died mid-flight — a finished brain is never
handed over. Every clean failure path (too many files, nothing uploaded, nothing
readable, nothing ingested) drops its own claim, so a rejected upload cannot
squat a name.

`migrations/versions/0006_brain_claim` (default `'ready'`, so pre-existing rows
keep their meaning) applied to lab and live, each after a `pg_dump`. Proved by
`tests/test_brain_claim.py` — 20 checks wired into `verify.sh` as
`[brain-claim]`, driving the real race with two concurrent multipart uploads from
two identities and asserting one 200, one 409, one `ready` row, the loser told to
retry rather than silently merged, and the winner's brain unreadable to the
loser.

Battery green, twelve suites: documents 25/25, pipe-states 13/13, connectors
90/90, tenants 10/10, smoke 4/4, frontend-transport, frontend-css,
chat-integrity, brain-claim, ui-react, clerk-gate.

**Verification no longer writes into the demo database.** `./verify.sh` used to
fall through to `.env` — the live database — so every routine battery left test
chats inside the demo brain, stamped as nobody's because the battery runs
`AUTH_MODE=off`, which is precisely the population the SEC-5 grandfathering rule
shows to every tenant. It now picks the lab when reachable, refuses the live
database unless `KESTREL_ALLOW_LIVE_DB=1`, and stays quiet when there is no
database at all (CI). A side effect of choosing the lab: `chat-integrity` and
`brain-claim` now run on a plain `./verify.sh` instead of being skipped.

`ops/backfill_chat_owner.py` makes the remaining SEC-5 decision executable rather
than rhetorical: dry run by default, one transaction, reversible through the JSON
it writes, and it refuses to invent an owner — a chat whose brain carries no
ownership record, or is still a `'creating'` claim, is reported and left NULL.
Measured on live: 2 chats / 8 turns, both resolvable to `company_brain`'s recorded
owner. **Not applied**: stamping who owns legacy history is the owner's call, and
the grandfather branch comes out with it.

With M4 gone, every defect ever recorded in `BUGS.md` and `BUGS_AUDIT.md` Round 1
is closed; the open list is `BUGS_AUDIT.md` Round 2's residual — the NULL-org
chat backfill, which is an owner decision, not a bug.

## Cutover finished and audit Round 2 closed 2026-10-04

Continued the handover below. The platform is now the built React app on `:8000`
and every Round 2 defect is fixed with a check that fails if the guard is removed.

**Migrations, deliberately.** Live `:5433` went `0003 → 0004 → 0005` with a
`pg_dump` before each (Homebrew's `pg_dump` is v14 against a v17 server, so the
dump runs inside the container). Alembic needs `DATABASE_URL` exported: `env.py`
only rewrites the DSN to the `psycopg` dialect when that variable is set, and
`psycopg2` is not installed — pointing at `alembic.ini` alone dies on import.
`0005_chat_tombstones` is new from this pass. Lab (`:5434`) was migrated first
and everything below was rehearsed there.

**Round 2 (CH-1…CH-13) — closed.** The headline is CH-1: a chat save rewrites
`turns` wholesale while both clients sent only their last 60 turns, so the 61st
message deleted turns 1..60 silently and permanently. Now a save carrying fewer
turns than the database holds is refused (409) unless it *declares* a trim, both
clients send the whole conversation, and the cap comes from `/api/config` so the
server's number and the client's number cannot drift apart again. Deletions are
remembered (`deleted_chats`): a POST with a deleted id gets 410 Gone and the
client moves the conversation to a fresh id instead of resurrecting the one the
user threw away. `DELETE` answers 404 when it removed no rows, which is what the
route's own comment always claimed. Filing a chat under a brain is now a brain
access like every other write. `_ts` accepts the ISO string the server itself
returns, so restored turns keep their real times. The list reports `total` and
`truncated`. `get_chat` reads chat and turns in one transaction, and a psycopg
error on any chat route is a 503 that also clears the cached availability verdict
instead of becoming a 500.

**CH-4 and CH-13 were found in the browser, not in the code.** At 1440 the chat
row's left 34px belonged to the row rather than the link (clicks vanished while
the cursor promised a pointer) and the invisible delete button still hit-tested,
so a mobile tap there armed delete instead of opening. Fixing the padding
exposed CH-13: `openChat` wrote `?chat=` without clearing `?view=`, so opening a
chat from another view left a contradictory URL and a reload dropped the user
back on Brains with the conversation invisible — the exact symptom the owner
reported, and the defect the crashed client audit had reproduced but never
filed. Both are now locked: four new gates in `check_ui_react.py`, and the
owner's two symptoms pass end to end (open a chat from Brains → survives a
reload; delete → it does not come back).

**Verification.** New `tests/test_chat_integrity.py` (19 checks) wired into
`verify.sh` as `[chat-integrity]` — lab-only because it writes rows, cleaning up
after itself. Battery with `KESTREL_CLERK_GATE=1` on the lab database: documents
25/25, pipe-states 13/13, connectors 90/90, tenants 10/10, smoke 4/4,
frontend-transport, frontend-css, chat-integrity, ui-react, clerk-gate — 0
failing. `test_auth_isolation.py` had to become re-runnable: durable tombstones
made its fixed fixture id collide with its own deletion on a second run.

**One fix needed a second attempt**, recorded because the first looked right:
CH-12's gate read `authMode !== "clerk"`, but the mode starts as `"unknown"`
until `/api/config` resolves, so the prefetch still fired signed-out. Verified
afterwards by network evidence on the live server — a signed-out load makes
exactly one backend request, `/api/config`.

That correction broke `tests/test_react_clerk.py`, and the test was the thing
that was wrong: its single control run conflated **a session that cannot mint a
token** (must still ask, 401, and show the server's words) with **no session at
all** (must not ask). It now drives three profiles — token, noToken, signedOut —
and the sidebar's signed-out state says "Sign in to see your chats" instead of
inventing an empty history.

**Browser audit tail closed, and it found one more (CH-14).** Light/dark parity
was measured by computing real rendered contrast in the page at 1440 and 390 in
both themes — every checked surface clears WCAG AA (worst 5.84:1 on the sidebar,
most above 11:1) with no page errors. Mid-stream brain switching turned out to be
a genuine data-integrity defect: `handleBrainChange` neither aborted the running
ask nor cleared the thread, so brain A's conversation stayed on screen under
brain B and the next save filed it into B — while the switcher's own confirm text
promised "this starts a fresh chat". It now aborts, blanks the thread in state
*and* on the ref (the aborted ask's save effect can fire before React commits),
and drops the stale `?chat=`. Two new acceptance gates lock it, alongside the
four for CH-4/CH-13.

**Live state:** `:8000` serves `frontend/dist` (React) with `AUTH_MODE=clerk`,
`/brains` and `/upload` 307 into the app, `/graph` still legacy (D-2), DB at
`0005`. Remaining: the owner decisions below, plus the audit tail (light/dark
parity and mid-stream brain switching have never had a browser pass).

## Session handover — React port landed, cutover unfinished 2026-10-04

State at 00:32 IST. The previous working session was cut off at 00:18 by a
provider quota error (`402 ACCOUNT_QUOTA`) **mid-step**, not at a boundary: its
last message was "While the audits run, let me do the migration", and the
cutover it intended never happened. Its todo list had all 15 Phase C–E items
complete; the bug hunt, the 0004 migration and the legacy-page retirement were
never added to it, so there was no checklist for what remained.

**Verified current state (measured, not narrated):**

- `main` @ `60f87a1`. React port Phases A–E are committed: the backend serves
  `frontend/dist` behind `KESTREL_UI` (default `react`), `frontend/dist` ships
  with a CI staleness gate, `verify.sh` now runs `check_ui_react.py` in place of
  the retired `check_ui.py`.
- **11 files of uncommitted turn-7 work**: turn-detail persistence
  (`turns.steps/worked_ms/stopped/error`) in `storage.py` +
  `migrations/versions/0004_turn_detail.py`, the `chats_get` 404 contract, a
  bounded `list_chats`, org-scoped `delete_chat`, retirement of
  `static/brains.html` + `static/upload.html` behind 307 redirects, and the
  matching `App.tsx` / `Sidebar.tsx` / `lib/api.ts` / `index.css` changes.
- The static gates pass on the dirty tree: `tests/test_frontend_api_transport.py`
  → "every /api call goes through apiFetch, and the served bundle is complete";
  `tests/test_frontend_css_utilities.py` → PASS. The bundle is fresh (built
  00:14, after the last src edit at 00:13).
- `SEC-3` / `LOW-10` from `BUGS_AUDIT.md` confirmed fixed live: `/api/brains` and
  `/api/brains/{name}/events` now 401 unauthenticated (were 200).
- **The stack was DOWN when this was written** — colima stopped (its fourth such
  incident), taking Postgres, Cognee and Langfuse with it. `/tmp/kestrel_app.log`
  ends with the old `:8000` process throwing
  `RuntimeError: File at path …/static/upload.html does not exist` and then
  shutting down. That is the half-cutover showing up as a user-visible 500 on
  `/brains` and `/upload`: the process was still pre-cutover code while the
  files were already deleted.
- Schema drift: the **live** DB (`:5433`) is at alembic `0003_job_staging` and its
  `turns` table has none of the four new columns; only the **lab** (`:5434`) got
  `alembic upgrade head`. Booting the current code self-heals the columns via
  `storage.init()`'s `ALTER … IF NOT EXISTS` but leaves `alembic_version` at 0003.

**Round 1 is closed, Round 2 is open.** All 45 items of `BUGS_AUDIT.md` were
worked by ID and are fixed in the tree (each fix carries an in-code comment
naming its audit ID); the closure is code-audit plus the two live measurements
above, and still needs one `./verify.sh` run to be worth repeating. `BUGS_AUDIT.md`
now opens **Round 2** — the chat subsystem (CH-1…CH-11), whose headline is silent
permanent history loss (`App.tsx:694` saves only the last 60 turns over a
wholesale replace) plus the delete-that-reports-success-and-resurrects pair, which
is the owner's own reported symptom.

**Next, in order:** bring the stack up (`./ops_stack_up.sh`, idempotent) and
choose deliberately between `alembic upgrade head` on live vs letting `init()`
self-heal → triage `check_ui_react.py:447` ("sheet targets the row's brain") →
`./verify.sh` green → commit the turn-7 work → CH-1/2/3 as one change → CH-4 in a
browser → CH-6 → the rest, then finish the client-side audit that never completed.

**Still parked for the owner:** the NULL-org legacy chat backfill (the last
standing cross-tenant visibility hole, `storage.py` `_owner_clause`), `D-2`
graph surface for beta (`/graph` is now the only non-React route), `D-3`/`D-4`
connectors and v2-jobs scope, and whether to archive the stale untracked
`ZCODE_HANDOFF.md` (28 Sept, Langfuse/OCR era) so the doc set stays trustworthy.

## P6 connectors UX pass — the shelf stopped lying 2026-09-29

Built the OAuth+vault layer, then drove the shelf in a real browser as the
signed-in owner. Four things were rendering states the backend could not serve.

  * A Connect button sat next to a "Coming soon" pill on the Gmail row. Both
    at once, meaning opposite things; pressing it 503s. Connect is now gated
    on the instance actually having an OAuth client registered.
  * Import controls were always live even with nothing connected — same lie,
    one click deeper. Inputs and the Import button now disable, so the shelf
    offers no action it cannot perform.
  * The inverse bug, found immediately after: gating Disconnect on
    `configured` too meant that removing the OAuth client from an instance
    orphaned a live grant with no way to revoke it. Disconnect is now gated
    on whether a grant EXISTS, which is the right question.
  * `/api/connectors/status` reported `slack_read: true` while the grant sat
    in `needs_reconnect` — the one state where the transport definitively
    cannot serve an import. `slack_read`/`gmail_read` are now `== "connected"`.

Verified in the browser against a seeded owner grant, not by reading the code:
unconfigured renders pill-only with imports disabled; a live grant renders
"Connected" + Disconnect + enabled imports; clicking Disconnect flips that row
to "Coming soon" and leaves Slack untouched (per-row isolation); a
`needs_reconnect` grant shows the warn pill and stops advertising the read
transport. The Disconnect click round-trips through the real
`POST /api/connectors/disconnect` and re-renders from the refreshed status.

Suite grew 84 -> 90 checks to lock the last two in: a dead grant must not
advertise gmail/slack read, and the env token alone must. Battery green:
documents 25/25, pipe-states 13/13, connectors 90/90, tenants 10/10,
smoke 4/4, UI PASS.

Also pinned `pydantic-ai-slim[openai]==2.51.0` in requirements.txt — the line
that shipped the P6 agent layer had been left unpinned while every other
dependency in the file is exact, so a container rebuild was not reproducible.

## P6 connectors part 1 — OAuth connect flow + encrypted token vault 2026-09-29

Connectors were four read-only rows behind a "Coming soon" pill. They now have
a real connect path: the browser never sees a token, and a grant that dies
degrades to "reconnect" instead of erroring mid-sync.

New `connectors.py` — five layers, each independently testable:
  * `PROVIDERS` registry: Google + Slack authorize/token URLs and MINIMAL
    scopes. Gmail + Drive read-only; Slack gets channels/groups history and
    users:read. `chat:write` is deliberately absent from the read grant —
    sending keeps using the separate approval-gated path.
  * Fernet vault in a `connector_credentials` table keyed (provider, owner_key)
    where owner_key is `org_id|user_id` — the same identity shape as
    `storage._owner_clause`, so a grant can never outlive the tenant that made
    it. Key comes only from `CONNECTOR_VAULT_KEY`; no key means reads behave
    as unconfigured and WRITES RAISE rather than silently dropping a grant
    (a silently-dropped OAuth grant is the worst possible failure: the UI
    says "connected" and everything 401s later).
  * Server-side `state` binding: random token -> {identity, provider, exp}.
    Single-use, and consumed by ANY pop attempt including a wrong-provider
    one — an attacker who can probe states cannot test one against several
    providers and keep a live token usable.
  * `google_access_token()` — the whole reason this design exists. Access
    tokens live ~1h. Expired -> silent refresh + persist rotation. A provider
    refusal that means the grant is GONE (invalid_grant / invalid_token /
    unauthorized_client) flips the row to `needs_reconnect`. A transport blip
    (DNS, timeout, 5xx) does NOT — it hands back the stale token and leaves the
    row connected, because a flaky network must never force a re-consent.

`app.py`: `GET /api/connectors/oauth/{provider}/start` (302 to consent),
`GET .../callback` (validate state -> exchange -> encrypt -> `/?connected=`),
`POST /api/connectors/disconnect`. `/api/connectors/status` now reports an
`oauth` block with per-provider `configured` + `state`, and `slack_read` /
`gmail_read` fall back to the legacy env token only when one is actually set.
Gmail import prefers the OAuth grant (Gmail REST) and falls back to IMAP app
password; Slack import resolves the vault token before `SLACK_BOT_TOKEN` and
downgrades to needs_reconnect on `invalid_auth`.

UI (`shell.js`/`shell.css`/`index.html`): the shelf splits into "Read into
brains" and "Send on approval", OAuth rows get real Connect/Disconnect buttons
in a popup flow with polling, and both import paths are driven from the sheet
with inline result notes. `/` toasts the OAuth landing and strips the query
params so a reload does not re-toast.

Bugs found and fixed while testing (all caught by the new suite, not by hand):
  * NULL `expires_at` made Postgres unable to infer the param type —
    `IndeterminateDatatype` on every Slack-style no-expiry write. Fixed with an
    explicit `::double precision` cast.
  * `connection_state(env_fallback=True)` returned "connected" when NOTHING was
    configured, so a fresh instance advertised two transports it could not
    serve. Signature now takes the env token itself and checks it is non-empty.
  * An orphaned `try {` in `rememberChat()` (left by a reverted edit) broke
    every script in index.html — the UI battery caught it as a console syntax
    error while all four other suites passed.

New `connectors_test.py`, 84 checks, wired into `verify.sh` as suite 3. Runs
in-process via TestClient with the token endpoint stubbed, so it needs no
network and no browser: covers ciphertext-at-rest, refresh rotation, revoked vs
blurred distinction, cross-identity isolation, state forgery/replay/burn, and
that no token material ever reaches a client response. Battery: documents
25/25, pipe-states 13/13, connectors 84/84, tenants 10/10, smoke 4/4, UI PASS.

Still to do in P6: cursor-based sync workers (Gmail historyId, Drive changes
tokens, Slack per-channel cursors) + the checkpoint table, and MCP send behind
the existing approval gate. Both need a registered OAuth client to exercise
for real; `PUBLIC_BASE_URL` and the vault key are in `.env` (gitignored) and
the suite passes a fake client so the flow is proven without credentials.

## Router sub-agent — non-brain queries bypass retrieval 2026-09-27

Owner request: queries unrelated to the brain must fast-track. Design: the
orchestrator launches a ROUTER sub-agent concurrently with the retrieval
racers — a tiny classification call (fixed instruction prefix, cache-hit
friendly, ~1-2s) deciding BRAIN vs CHAT. CHAT cancels the racers and answers
via a direct completion (time-aware: current datetime in the prompt); BRAIN
lets the racers continue with zero added latency. Router failure or ambiguity
defaults to BRAIN (a misroute to retrieval costs seconds; a misroute to chat
costs trust).

Measured: "What time is it here?" — router bypasses, correct datetime answer,
9s total (was 11-25s through the brain). Brain questions unchanged (5
citations; routing overlapped, not additive).

## Stale-citation healing on restore — 2026-09-27

Chats saved before the smalltalk fix carried fake citations on greetings and
re-rendered them on restore. Fix: restoreHistory now heals local-only chats by
pushing them through the server's authoritative strip (POST -> GET) before
rendering; storage.upsert_chat strips sources from smalltalk AND social-reply
bot turns (memory_layer classifiers are the single source of truth). Narrow
JS guard kept for fully-offline rendering. Verified: stale seeded chat renders
0 citations on both turns.

## Smalltalk classifier v2 — social-vocabulary based 2026-09-27

Owner flagged the logic gap: "hello how are you" fell through the narrow
greeting regex into a 30.8s retrieval that cited random documents for a
greeting. Rewritten as social-vocabulary classification (greetings +
how-are-you + thanks + identity + goodbyes, optional filler words, <=8 words,
greeting+social sequences) instead of exact-string whitelisting. Verified:
22-case matrix, 0 misroutes. Fake citations for greetings are now impossible
(smalltalk path never touches the brain).

## Smalltalk latency root cause — FIXED 2026-09-27

"hii" as a follow-up took 19-26s: the flag died at the recall->_cloud boundary
(the wrapped query defeated the regex) AND the app restart had dropped the
local-brain env. Fixed: flag threaded end-to-end (app raw q -> recall ->
_cloud -> orchestrator), .env now durably points at localhost:8888 (flavor
oss, timeout 1800), greeting template judged on the wrapped query's last line.
Measured: follow-up "hii" completes in 2.2s (was 19-26s); pure greetings are
instant templates; chatty smalltalk = one direct completion.

## P2 — persistence + metering + summarization + fast paths — COMPLETE 2026-09-27

- Postgres 17 in compose (kestrel-db); chats/turns/llm_calls schema in storage.py;
  server-first restore with localStorage offline fallback; deletes sync both ways.
- Token metering: every ask records feature/brain/model/est-tokens/ms into
  llm_calls; GET /api/usage aggregates. Estimates = chars/4 (labeled).
- /api/summarize: real LLM rolling summaries (platform key, gpt-oss-120b).
- Smalltalk fast paths: pure greetings = instant template (0s, was 11-26s);
  chatty smalltalk = direct LLM completion (~5s), NO brain round trip.
- Known: DeepSeek V4.1 Flash recall via OpenRouter flaps 402 upstream
  (works for ingest + raw calls; recall moved to gpt-oss-120b). Revisit with
  a funded OpenRouter balance or a direct DeepSeek API key.
- Brain volume incident recovery documented in P1 entry; new state 246/587.

## P1 — THE FLIP: app answers from OUR local brain — COMPLETE 2026-09-27

- Colima resized to 4 CPU / 8 GB (the 2/4 sizing starved recall into timeouts).
- DeepSeek V4.1 Flash validated for INGESTION via OpenRouter (graph built:
  178/387 nodes/edges, $0.02 spend). Recall on DeepSeek flaps 402 at the
  upstream — recall runs on gpt-oss-120b (both models stay in the registry).
- INCIDENT (diagnosed + recovered): a debug container + hard colima restart
  wiped the brain volume (178/387 lost). Volume ownership fixed (chown 1000),
  corpus re-ingested on gpt-oss-120b. New state: 246 nodes / 587 edges.
- App flipped: `COGNEE_SERVICE_URL=localhost:8888`, flavor oss. Parity verified
  in-browser: real orchestrator worklog, correct answer (Marcus Lee / Priya
  Raghavan), 3 local citations. Battery green (25/25, 13/13, 10/10, smoke 4/4).
- M1.4 measurements: brain container 1.29 GiB RSS (fits 2 GB, comfortable at 8);
  ingest wall ~9 min (12 docs, extraction-dominated); recall ~11.7s warm local
  (beats the 18-26s cloud tenant on this machine).
- Note: app footer says "cloud · ready" — cosmetic: "cloud" = any Cognee API;
  it is actually localhost:8888.

The Phase 1 gate of the old plan is PASSED: the product answers from our own
brain on our own keys. Next per PLAN.md: P2 (Postgres persistence + Langfuse).

# PROGRESS — execution log for BUILD_PLAN.md

Append-only, newest first (BUILD_PLAN.md §4). States are exactly:
`DONE` | `BLOCKED` (points at a BLOCKERS.md entry) | `WAITING-HUMAN` | `SKIPPED`
(SKIPPED only ever carries a one-line reason + recorded human approval).

## M2.2 — graph-store decision F2: postgres_graph_shared ISOLATES — DONE 2026-09-28

Env discovery: 1.6.1 selects via GRAPH_DATABASE_PROVIDER (postgres_demo is
canonical, "postgres" alias kept) + GRAPH_DATASET_DATABASE_HANDLER
(default "ladybug"); the Postgres hybrid adapter is out-of-tree (only
Neptune remains). Both PostgresGraph handlers exist in-tree.
Experiment on scratch m22_probe_*: ingest→COMPLETED→recall returns ONLY the
probe (mango/2031, zero demo keywords), graph 11 nodes (vs 295 global on
embedded). Kill→restart→recall identical (state survives in Postgres).
contract_test --flavor oss green on the backend. Side note: drift probe now
200s cloud names (was 422 on embedded) — different code path, harmless (we
send oss names). **F2: postgres_graph_shared is the local multi-brain
answer** (docs' "demo, not production" notwithstanding — measured).
Reverted to embedded after (demo protection); scratch deleted, tenant clean.

## INCIDENT — M2.2 revert wiped the demo graph — RECOVERING 2026-09-28

Root cause: the ONLY mounted path was /app/.cognee (logs+ids); live data
lives under /cognee-storage (DATA/SYSTEM_ROOT) on ephemeral disk. My
--force-recreate destroyed company_brain + registry (295 nodes). The M0.2
volume comment was wrong about what it preserves. Fix: compose.oss.yml now
mounts cognee_oss_data:/cognee-storage (plus O2 restart/healthcheck already
in). Recovery: 12-doc corpus re-ingesting into company_brain (OpenRouter
key, fastembed local) in background; fixtures snapshots still serve
read-only meanwhile. Postgres (30 chats) untouched throughout.

## Round 2 — 20 new ops/security finds — DONE 2026-09-28

Second hunt (ops-failure + security-2nd-pass lenses) found 20, all fixed +
proven except where noted OWNER ACTION:
- S1 upsert-hijack guard (OwnershipError→404) · S2 unregister-on-delete ·
  S3 create-vs-append split (fail-closed overshoot broke ALL creates — fixed:
  identity-first, owner-check only on existing) · S4 iss-pin + org claim
  fallbacks · S6 error truncation + storage-status redaction · S7 demo
  fallback key · S8 normalized RESERVED · S9 safe response headers +
  per-identity token buckets (ask 60/upload 20/events 30 per min, env
  overridable) · S10 snapshot read validation.
- O2 storage self-heal retry + compose restart/healthcheck · O4 cached
  upstream probe (30s TTL, stale-on-failure) · O5 llm_calls index + 180d
  purge · O6 upsert caps (500 turns, 100k chars) · O7 clerk-misconfig boot
  refusal + audibility · O8 per-file atomic snapshots · O1 render.yaml
  DATABASE_URL/Auth placeholders.
- Battery green again (25/25, 13/13, 10/10, 4/4, 5/5 isolated, UI clean).
- OWNER ACTION required: O3 — fixtures/uploads.json commits a Bedrock key
  fragment + account id. Rotate the key, scrub history; migrating the
  manifest to a gitignored path is a follow-up call (breaks existing
  citations without migration). O9 (ingest receipts/resume) is a design
  task, recommended for P4.

## Owner decisions 1–4 — DONE 2026-09-28

1. Legacy chats → owner org (b): 26 NULL rows stamped
   org_3JvGk0RrREUOodUd1KkANvi2vGB/creator; chats gained created_by (migration)
   for org-less owners; predicates are org-OR-creator with double-NULL
   grandfathering. Proven: owner lists 27, stranger 0.
2. Demo NOT world-readable: company_brain row flipped to creator-owned
   (shared=false); DEMO blanket-allow removed — every brain, same rule.
   Proven: owner ALLOW, stranger 403, unknown 403.
3. Deletes tightened to org/creator-match (legacy double-NULL still deletable
   until stamped — none remain).
4. Hedged retrieval (1x cost, same speed): GRAPH first, RAG starts only past
   KESTREL_HEDGE_SECONDS=8 or on fast failure; router concurrent as before.
   Proven by stub: fast graph 1 call, slow graph hedges (2 calls, vector wins).
   (One probe detour: live router classified "test q" as chat — correct
   behavior, wrong probe query; re-probed with forced route.)
Infra: colima was down (restarted; volumes intact, 26 chats kept);
test_auth_isolation now runs on isolated kestrel_test_auth DB (fail-closed
made prod-DB testing unsafe — the suite proved it by failing).

## Bug-fix session — BUGS_AUDIT.md 45 + 14 new — DONE 2026-09-28

DeepSeek v4.1 Flash audit validated TRUE 45/45 (3 subagent sweeps + execution
proofs for SEC-1/SEC-2). Own hunt added 14: NEW-1..4 (read-route
normalization gaps, stats traversal, chats brain filter, split-brain) + H1..H10
(H1 was my M0.3 regression — fixed; H2 blocks SEC-8; H9 402-retries; H10
PROVIDER-freeze vs loopback rule). All fixed, each proven by execution or
suite; full battery green (25/25 docs, 13/13 pipe-states, 10/10 tenants, 4/4
smoke, 5/5 auth isolation, UI zero console errors).

Decisions taken (owner-absent, safe defaults): legacy NULL-org rows
grandfathered visible/deletable, new writes server-stamped; demo dataset
explicit allow (fail-closed everything else, incl. DB outage); race kept
(2x-cost documented) with KESTREL_RACE_RETRIEVAL=0 lever; SEC-5 backfill still
wants a real owner call. Incidents: colima VM was down (restarted, 26 chats
intact); one pkill caught the live server (restarted immediately).

## M1.1/M1.2 — warm routes + light-mode trial LIVE on OpenRouter — UPDATE 7, 2026-09-25

Human provided an **OpenRouter key** (free tier, $250 cap, $0 used) for a
light-mode trial and asked that **all provider routes stay warm**.

**Warm-route table (new `provider_check.py`, run inside the container):**

| provider | verdict |
|---|---|
| openrouter | **LIVE** (real key, real answers) |
| openai, groq, cerebras, anthropic, deepseek, z.ai | WARM (401 at dummy key — route proven) |
| bedrock | WARM (account pending verification; key wired) |
| azure | CONFIG-WARM (litellm maps the model string; endpoint testable when the human's resource exists) |
| ollama | SKIP (dormant by design) |

Any new key = uncomment its block in `.env.oss` + restart the container.

**Active: OpenRouter `openai/gpt-oss-120b`** (the human's chosen model; free
pool congested, paid path costs cents; reasoning model ≈118 tok overhead).
Embeddings: keyless fastembed/384.

**INCIDENT (fixed):** after the OpenRouter swap, the whole contract test went
401 — one of my `.env.oss` block-editing rewrites had commented out the
auth-off vars (the commenting loop's stop marker precedes the section it
edits, so it ran to EOF) and the active embedding lines were lost with the
bedrock block. Fixed by surgical rewrite + **post-edit assertions** in the
rewrite script (exactly one active LLM block, embeddings active, auth vars
uncommented). Lesson recorded: never trust string-surgery on the env file —
assert after every edit.

**Contract test vs local OSS: 11/11 PASS** — first fully-real run (terminal
`DATASET_PROCESSING_COMPLETED -> success`, real recall text, zero skips).

**M1.2 light mode: PROVEN.** 2-doc slice (Bluepeak MSA + P1 ticket) ingested
into a scratch dataset on local OSS; flagship question ("Why is the Bluepeak
renewal at risk...") returned a genuine cross-document answer — outage
breaches 99.9% SLA at 99.89%, 10%/20% credit ladder — with evidence chunks
from BOTH documents. Scratch deleted after.

Next: full 12-doc corpus ingest (est. $0.10–0.50 of the cap, ~20–40 min),
then M1.3 (app parity) and M1.4 (measurements).



## M1.1 — ROOT CAUSE IDENTIFIED: AWS account pending verification — UPDATE 6, 2026-09-25

Human confirmed the region is **eu-north-1 (Stockholm)** — `AWS_REGION` set
accordingly in both env files. Container key hash verified byte-exact against
the pasted key (an earlier mismatch was a newline artifact in the checker).

- Probed eu-north-1: `global.xai.grok-4.6` visible (43 profiles; no gpt-oss
  profile anywhere in any region — gpt-oss is region-scoped `openai.*`),
  both grok-4.6 and gpt-oss-120b → `Operation not allowed`.
- **The verdict, stated verbatim by Bedrock itself** in ap-south-1 and
  eu-west-1: *"Your account is currently being verified."* The account is
  new / pending Bedrock use-case verification. That single fact explains
  every refusal since morning across 4 regions, 2 keys, 11 model IDs, and
  both API paths — including the earlier "Too many tokens per day".
- **Nothing remains to fix in our stack.** Keys: correct and authenticated.
  Wiring: verified byte-exact. Config: human's chosen model + fastembed,
  region eu-north-1. The only unblock is AWS finishing account verification
  (user should check email + Bedrock console → Model access → use-case
  status; new accounts require submitting the use-case form).
- When verification clears: `contract_test.py --base http://localhost:8888
  --flavor oss` → M1.2 corpus ingest. Zero rework.



## M1.1 — second Bedrock key tested; wall confirmed account-level — UPDATE 5, 2026-09-25

Human supplied a SECOND long-term Bedrock API key (same account 799823514509).
Swapped into `.env.oss` (only place it lives), container recreated, probed
gpt-oss-120b: **same `Operation not allowed`**.

Two keys × identical refusal × (11 model IDs × both API paths) = the block is
account-level, not key-level. What remains, all on the AWS console side
(us-east-1):
1. **Model access**: Bedrock → Model access — enable `openai.gpt-oss-120b`
   (third-party models need explicit enablement; a brand-new account may
   have nothing enabled, which matches every probe).
2. **Daily token quota**: the first call of the day got "Too many tokens
   per day"; even with access enabled, the day-cap must reset.
When either clears: config is already correct (gpt-oss-120b + fastembed/384);
next action = `python3 contract_test.py --base http://localhost:8888 --flavor oss`
→ M1.2 corpus ingest. No rework.



## M1.1 — Bedrock key + gpt-oss-120b wired; account refuses all invokes today — UPDATE 4, 2026-09-25

Human's model choice: **gpt-oss-120b** on the Bedrock key. Active block is now
`bedrock/openai.gpt-oss-120b-1:0` + keyless fastembed/384. Container healthy.

- Probed BOTH Bedrock API paths (`invoke/` and converse) for gpt-oss-120b:
  both `Operation not allowed`. Cumulative refusal list today (all identical
  error since the first call's daily-token message): sonnet-4, haiku-3.5
  (also EOL), nova-micro, nova-lite, llama3.1-8b, titan-embed-v2,
  grok-4.6 (us + global profiles), gpt-oss-120b (invoke + converse).
- Conclusion stands: the account's daily token wall tripped during probe 1;
  model choice is irrelevant until it lifts (or until model access is
  enabled in the console). Zero rework needed when it does: the active
  config is already the human's choice; next action = contract test → M1.2.
- gpt-oss-120b ALSO runs free on Groq (same weights, `openai/gpt-oss-120b`
  via api.groq.com/v1) — a Groq key would run the identical model today.

## M1.1 — Bedrock key wired; account daily token cap is the blocker — UPDATE 3, 2026-09-25

Human clarified the key is for **Grok** — "grok 6" is **Grok 4.6** on Bedrock.
Listed the account's inference profiles WITH the bearer key (control plane
accepted it: 87 profiles) — the Grok profiles are `us.xai.grok-4.6` and
`global.xai.grok-4.6`.

- Active block now: LLM `bedrock/us.xai.grok-4.6`, embeddings switched to
  **keyless fastembed/384** (Titan was refused on this account; nothing has
  been ingested yet, so the dimension switch is free). Container healthy.
- Both Grok profiles currently return `Operation not allowed` — same as every
  other model after the first call's `Too many tokens per day`. Two
  non-exclusive causes, both on the AWS side: (1) the daily token budget
  tripped in the first probe, (2) xAI model access may not be enabled yet
  (Bedrock console → Model access → enable Grok 4.6).
- When either clears, the setup runs as-is: contract test → M1.2. Block G in
  `.env.oss.example` records the profile IDs and the fastembed pairing.

Human supplied a **long-term Bedrock API key** (CSV in Downloads; stored ONLY
in gitignored `.env.oss` — never echoed, never tracked).

- Active block switched to Bedrock: `AWS_BEARER_TOKEN_BEDROCK` + `AWS_REGION=
  us-east-1`, LLM `bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0`,
  embeddings `bedrock/amazon.titan-embed-text-v2:0` / 1024 dims. The dormant
  ollama block is fully commented out (no var collisions). Template block G
  now documents both auth paths (API key vs SigV4 creds).
- **Auth and routing VERIFIED**: the first direct LiteLLM probe authenticated
  (Bearer accepted) and reached Bedrock's quota layer — no AccessDenied, no
  signature errors, container healthy after recreate (~24s).
- **Blocker: the account's daily token budget.** First sonnet-4 call:
  `Too many tokens per day, please wait before trying again`. Every subsequent
  call (sonnet-4, nova-micro/lite, llama3-1-8b, titan-embed-v2) then returns
  `Operation not allowed` — the error CHANGED after the first call, i.e. the
  day-cap tripped mid-probe. Not a wiring/permission issue.
- Probe matrix recorded for the record: sonnet-4 → quota → not-allowed;
  others → not-allowed; claude-3-5-haiku → end-of-life on this account.
- Nothing to fix in our stack. When the budget resets (or the account raises
  its quota / enables model access in us-east-1), the SAME setup runs as-is:
  rerun `python3 contract_test.py --base http://localhost:8888 --flavor oss`
  then M1.2. Alternative for TODAY: any other provider key (e.g. Groq free)
  is one comment-swap away in `.env.oss`.
- Note: embedding dimensions are baked at first ingest. If the trial starts
  on fastembed/384 and later moves to Titan/1024, the corpus re-ingests.

## M1.1 — swappable-key layer complete; keys still pending — UPDATE 2026-09-25

Human decisions recorded: (a) the swap layer must cover **nine providers** —
OpenAI, Azure, OpenRouter, Groq, Cerebras, Anthropic, AWS Bedrock, DeepSeek,
Z.AI; (b) actual keys come later; (c) the keyless-local experiment was
abandoned mid-pull by human decision ("not important at this step") and the
space cleaned up.

- `.env.oss.example` is now the nine-provider registry (blocks A–I plus the
  keyless-local block), each a comment-swap + restart, no code changes.
- Keyless-local attempt — findings banked before teardown:
  1. Container reaches host Ollama via `host.docker.internal:11434` (verified).
  2. Cognee's `LLMConfig` requires ALL of model/endpoint/key even for Ollama
     — a non-empty dummy (`ollama-local`) satisfies it (in the template).
  3. fastembed model id must be `sentence-transformers/all-MiniLM-L6-v2`
     (384 dims) — bare `all-MiniLM-L6-v2` is rejected by TextEmbedding.
  4. **3B-class local models fail Cognee's strict structured-output schema**
     (llama3.2:3b → `SummarizedContent` ValidationError after LiteLLM
     retries; pipeline never completed). An 8B-class model is the local
     floor; a hosted key is the practical path.
- Cleanup per human instruction: pulled models deleted, partial blobs purged
  (~6GB reclaimed), `brew services stop ollama`. The keyless block is marked
  DORMANT in both env files with exact re-enable steps.
- OSS container remains healthy on :8888 (auth off, contract-verified in
  Phase 0); the app is up for preview on :8000 against the live tenant.
- STILL WAITING-HUMAN: one hosted LLM key (Cerebras block is pre-wired as the
  recommended default) + optional Gemini embedding key. M1.2 (corpus ingest
  into local OSS) starts the moment keys land.

## M1.1 — inference keys for the OSS container — WAITING-HUMAN 2026-09-25

Prep done: `.env.oss.example` template covers LLM_PROVIDER/MODEL/API_KEY/
ENDPOINT + LLM_RATE_LIMIT_REQUESTS=5 and EMBEDDING_PROVIDER/MODEL/DIMENSIONS/
API_KEY; var names confirmed against the running 1.6.1 container code
(`LLM_API_KEY` in settings/preflight/cognify modules, `EMBEDDING_DIMENSIONS`
in preflight). Per card, STOPPING here — human supplies: (1) LLM provider
choice (Cerebras `https://api.cerebras.ai/v1` or Groq) + API key,
(2) embedding choice (Gemini `gemini-embedding-001`/768 + key, or local
fastembed/384). Keys go into gitignored `.env.oss` only, never tracked files.
M1.2+ wait on this card.

Human answers 2026-09-25: (1) ALL of OpenRouter/Groq/Azure/OpenAI/Anthropic
must stay compatible — confirmed, all five route via LiteLLM
(OSS_STACK_AND_COMPETITORS.md §1.3); template now documents one commented
block per provider (A–F), Azure native via `azure/` prefix. (2) Embeddings =
doc default: Gemini `gemini-embedding-001`/768.
STILL WAITING on actual keys: one LLM key (which provider first?) + Gemini
embedding key (or say fastembed to go keyless). Nothing proceeds to M1.2
without `.env.oss` holding working keys.

Structure wired 2026-09-25 (no keys needed, all verified):
- `ingest.py`: `--base`/`--flavor` pass-through (absent = current env/cloud
  behavior byte-for-byte); key requirement waived for loopback targets ONLY
  (local OSS auth-off), cloud still always needs a key. `--help` + import
  clean, battery green.
- `.env.oss` (gitignored): full runtime structure, Cerebras-default LLM +
  Gemini/768 embeddings, both KEY lines blank — two lines to fill on arrival.
- App→OSS plumbing proven keyless: `PROVIDER=cloud
  COGNEE_SERVICE_URL=http://localhost:8888 COGNEE_FLAVOR=oss python3 app.py`
  → `/health` reports `service: localhost:8888, upstream: ready`.
  (Answers need keys — that execution is M1.2/M1.3.)

## PHASE 0 GATE — recorded 2026-09-25

Full `./verify.sh` green (documents 25/25, pipe-states 13/13, tenants 10/10,
smoke 4/4, ui PASS); contract test green on cloud (11/11) AND oss (11/11 +
1 no-llm SKIP by design); findings F1-negative recorded (M0.5). M0.1–M0.5 DONE.
Phase 1 unblocked.

## M0.4 — flavor switch for the two renamed recall fields — DONE 2026-09-25

`cognee_cloud.py` only (recall body): new `flavor()` (`COGNEE_FLAVOR`, default
`cloud`); `recall()` sends `search_type`/`include_references` on oss,
`searchType`/`includeReferences` on cloud. `terminal_kind` untouched.
Check: `contract_test.py --flavor oss --base http://localhost:8888` → PASS
(11/11, 1 SKIP); `--flavor cloud` → PASS (11/11); `./verify.sh --quick` green.

Two empirical confirmations: OSS **rejects** cloud names with 422 (drift is
loud — the switch is required, not cosmetic); cloud **silently accepts** both
(200). OSS keyless recall 422s `LLMAPIKeyNotSetError` — classified in
`probe_recall` as no-llm SKIP (harness refinement to `contract_test.py`,
documented in its docstring; full text checks rerun WITH keys after M1.1).
Note: OSS pipeline reaches COMPLETED keyless — only generation needs the key.

## M0.5 — record what OSS does with `filename` — DONE 2026-09-25

Finding **F1-negative**: OSS v1.6.1 stores `text_<hash>`, NOT the sent
basename — measured on two OSS runs (`text_8b1ffde9…`, `text_2e5c78b6…` vs
sent `probe_filename.md`) plus three cloud runs. Same behavior both flavors,
so `citations.py` content-fingerprint matching stays the primary path in
Phase 1; no code change (zero-code verification card as expected).

## M0.3 — contract_test.py — DONE 2026-09-25

`python3 contract_test.py --flavor cloud` → **11/11 PASS** (was 10/11).
`./verify.sh --quick` → documents 25/25, pipe-states 13/13, tenants 10/10,
smoke 4/4, exit 0.

Root cause of the one FAIL (terminal wait, 300s cap): NOT latency. Raw-payload
diagnostic (scratch `contract_diag_*`, polled every 15s, deleted after) showed
the cloud status endpoint returns a **bare string map** without
`include_error_detail` — `{"<uuid>": "DATASET_PROCESSING_COMPLETED"}` — which
`_status_values()` never yielded (dict-only), so `terminal_kind()` stayed None
even on COMPLETED. Pipeline actually completes in ~35s.

Two edits to unblock:
1. `contract_test.py::_status_payload` now sends `include_error_detail=true`,
   mirroring `cc.status()` (in-card file; the test now replays what the app
   actually sends).
2. `cognee_cloud.py::_status_values` also yields bare string values
   (M0.4-adjacent hardening, human-approved via "continue"; flat
   `{"status": ...}` still yields exactly once; 13/13 pipe-states green).

Findings banked: terminal `DATASET_PROCESSING_COMPLETED -> success`; cloud
stores filename as `text_<hash>` (reconfirms fingerprint design); cloud
silently accepts BOTH recall naming styles (200). Scratch deleted; tenant
left with the five real brains.

Next: M0.4 exactly as carded (flavor switch in `recall()` only).

## M0.3 — contract_test.py — IN PROGRESS 2026-09-25 (handoff point)

`contract_test.py` written per plan §2.3 (wf_smoke.py safety pattern: unique
scratch, collision refusal, finally-deletion). Validated against the CLOUD
tenant: **10/11 checks PASS** in its first real run —

- remember/status/data-items/data-raw/graph/recall(200, no 422) all conform;
  scratch auto-deleted.
- Findings already banked: **cloud stores our filename as `text_<hash>`**
  (confirms citations.py's content-fingerprint design is still required for
  the cloud flavor), and **the cloud tenant silently accepts BOTH recall
  naming styles** (camel and snake) — the drift signal there is silent, not
  loud, so the oss-flavor 422 check is the one that matters.

**The one FAIL:** `pipeline reaches a terminal state (300s cap)` — the status
map never satisfied `terminal_kind()` within 300 s on the cloud tenant.
Recall returned 200 mid-ingest (the known confident-answer trap), so the
skip-line now reports the actual kind rather than claiming "failed pipeline".
Diagnosis so far: NOT a shape issue (data items + raw round-trip work);
likely either (a) tenant queue latency > 300 s for `run_in_background=true`
with the status map possibly staying `{}` (no status key at all) while
queued — `_status_values` yields nothing for `{}`, which would look exactly
like this — or (b) a slow pipeline. A raw-payload diagnostic was started but
cut short for the handoff.

**Next agent, in order:**
1. Rerun the diagnostic (script sketch is in the HANDOFF.md): `remember` on
   a scratch dataset, poll `/api/v1/datasets/status?dataset=<uuid>` every
   15 s, PRINT each distinct raw payload. If `{}` persists, that is the
   answer: empty map while queued. Fix = longer default `--wait-timeout`
   (600–900) plus optionally reporting elapsed-queued as an INFO line; if a
   non-standard state string appears, extend `cognee_cloud._status_values`
   mapping instead (that is an M0.4-adjacent edit — see BUILD_PLAN.md M0.4
   before touching `cognee_cloud.py`).
2. Green cloud run → mark M0.3 DONE, commit.
3. Proceed to M0.4 exactly as carded (flavor switch in `recall()` only).

Leftover scratch from the cancelled diagnostic (`contract_diag_*`) was swept
from the tenant — dataset list verified back to the five real brains.

## M0.2 — local OSS container (pinned, auth off) — DONE 2026-09-25
(human chose Colima via brew when Docker was found absent)

- Installed colima 0.10.3 + docker CLI 29.8.1 + compose 5.5.1 via brew (one
  retry needed: stale brew metadata aborted the first install; `brew update`
  fixed it). Compose plugin symlinked into ~/.docker/cli-plugins.
- `colima start --cpu 2 --memory 4` — VM up (x86 emulation available).
- **Correction to research + plan:** Docker Hub tag is `cognee/cognee:1.6.1`
  — NO `v` prefix (`v1.6.1` does not resolve; found via registry API).
  compose.oss.yml and BUILD_PLAN.md corrected. Digest:
  sha256:db0973f4b913d73daa4061bc19362cde6edc59d1be8243b6667fade364b06428.
- `compose.oss.yml` (gitignored; port 8888:8000, named volume for embedded
  state) + tracked `.env.oss.example` (both auth flags false, fixed JWT
  secret placeholder, commented LLM/embedding block for M1.1).
- Check results:
  - `curl localhost:8888/health` → `{"status":"ready","health":"healthy","version":"1.6.1-local"}` (≈30s after start; first boot runs migrations).
  - `docker compose ps` → Up.
  - **Auth-off proven:** `GET /api/v1/datasets/` unauthenticated → 307 → 200 `[]`.
    Note: OSS canonical path has NO trailing slash (FastAPI redirect); our
    client's trailing-slash URL still works because requests follows redirects.
- Observations (not fixed, per N6): none new.


## M0.1 — verification harness + workspace files — DONE 2026-09-25
(was BLOCKED; the two out-of-scope fixes were approved by the human and applied)

- Environment verified: Python 3.13.3, all requirements importable, port 8000
  free, `playwright-cli` present at check_ui.py's NODE_BIN path, `brew` present.
- `verify.sh` per plan §2.2, refined during the card: forces `PROVIDER=mock`
  for the whole battery, starts/stops its own server, refuses a pre-owned
  port 8000, runs each suite via its own standalone entrypoint (pytest is the
  wrong runner here — collects 2 of 13 and 0 of 10 checks), tenants runs
  `--with-tenants` against the battery's own server.
- **Found and fixed in scope:** stale `__pycache__` bytecode compiled in the
  original Ignite_Delhi workspace, executing since the repo was copied
  (preserved mtimes validated it). Caches cleared — this affected every suite.
- **Approved out-of-scope fixes applied (BLOCKERS.md resolved):**
  1. `test_pipeline_states.py::drive()` now sets/restores
     `memory_layer.PROVIDER` itself — the suite no longer depends on ambient
     `.env` saying `PROVIDER=cloud`; still zero network (status stubbed).
  2. `app.py::delete_brain` now evaluates `require_dataset_access` BEFORE the
     mock-mode guard — unauthorized DELETE gets 401/403 in every mode instead
     of a masking 400. No regression in cloud or authorized paths.
- Check output (`./verify.sh --quick`):

```
== Kestrel verification battery (PROVIDER=mock) ==
[documents] PASS  25/25
[pipe-states] PASS  13/13
[server] up (pid 83199, mock fixtures)
[tenants] PASS  10/10
[smoke] PASS  4/4
[ui] SKIP  (--quick)
== done: 0 failing suite(s) ==
```

- PROGRESS.md and BLOCKERS.md created; `.gitignore` gained
  `.env.oss`, `compose.oss.yml`, `cognee_oss_state/`.
- Observations (not fixed, per N6): `.gitignore` contains a duplicated
  `.playwright-cli/` block; `.zcodeignore` duplicates it as well;
  `create_brain` and `brain_events` share delete_brain's guard-before-authz
  ordering (same class, only delete_brain was approved); `pytest` is not in
  `requirements.txt` (installed globally here; the battery no longer needs it).

## P5 — Langfuse observability + route labeling — DONE 2026-09-28

`observe.py`: zero-dependency, fail-open Langfuse bridge (daemon thread +
bounded queue; no keys = silent no-op). Traced: /api/ask (with the route
actually taken — smalltalk/chat/brain — parsed from orchestrator stage
labels; require_dataset_access now returns the identity), the router's own
LLM call, summarizer, and OCR vision calls. Local Langfuse v2 container
added to compose.oss.yml (Postgres-only; UI signup; keys in .env).

Ingestion wire format learned the hard way: trace-create + separate
observation-create items, fields nested under `body`; nested observation
arrays and flat items are silently rejected (207 with errors array).

Verified: per-route, per-model token split observable — 'hii' →
route=smalltalk (236/33 tokens), Bluepeak → route=brain (236/223), router
call as its own generation. Battery green.

P5 remaining (deferred, not blocking): route→model mapping formalization
for premium BYOK (P6) and off-peak ingest batching. Routing itself
(smalltalk direct / router sub-agent / hedged racers) was already shipped.
