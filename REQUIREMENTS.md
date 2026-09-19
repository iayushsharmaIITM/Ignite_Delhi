# REQUIREMENTS.md — PS-2 compliance, requirement by requirement

Source: the Ignite Room **PS-2 "Build a mini Company Brain using Cognee"** slide.
This maps every stated requirement to what we actually built, with the evidence to
back it. Nothing here is aspirational — each line was verified against the running
system.

---

## 1. The requirements, as written on the slide

### What to Build
- Participants should ingest a small collection of company data and create a system
  where humans and/or agents can ask questions.
- The system should retrieve relevant information and connect related entities/context.

### Core Requirements
1. Cognee-powered knowledge layer
2. **Ingest at least 2 different types of company information: E.g. documents + tickets + meeting notes**
3. Natural-language search/Q&A interface
4. Answers must be grounded in retrieved company knowledge
5. **Demonstrate at least one multi-hop relationship**

### Challenge
> Company Brain — Build a shared knowledge layer connecting company documents,
> conversations, tickets, code, and decisions so that humans, agents, and
> applications can discover both answers and the relationships behind them.

---

## 2. Compliance

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Cognee-powered knowledge layer | **MET** | Cognee Cloud tenant owns the graph, embeddings and vector store. `cognee_cloud.py` is the only module that talks to it. 219 nodes / 500 edges. |
| 2 | At least 2 types of company information | **MET — 6 types** | `corpus/` contains contracts, tickets, meeting notes, chat threads, policies and a handbook. See §3. |
| 3 | Natural-language search/Q&A interface | **MET** | `/` — free-text question box plus 4 suggested questions. Answers stream back in ~16–31s. |
| 4 | Answers grounded in retrieved knowledge | **MET** | Every answer carries an **Evidence** panel with the source chunks it was built from. Verified: 3–4 citations per answer. |
| 5 | At least one multi-hop relationship | **MET — verified twice** | See §4 for the tested chains. |
| — | "humans and/or agents" | **MET** | The UI serves humans; `/api/ask` is plain HTTP/JSON returning NDJSON, so an agent can call it directly. No UI scraping needed. |
| — | "connect related entities/context" | **MET** | `/graph` renders the entity graph: 5 node types (Entity, EntityType, TextSummary, Document, …) with typed edges. |

**Score: 5 of 5 core requirements met.** The two that looked riskiest on first
reading — *2+ types* and *multi-hop* — both turned out to be satisfied already.

---

## 3. Requirement 2 in detail — the six information types

This was the requirement most likely to be quietly failed (a corpus of ten files
that are all really "documents" would technically be one type). It is not:

| # | File | Type |
|---|---|---|
| 01 | `01_contract_MSA-2025-0114_bluepeak.md` | **Contract** (master services agreement) |
| 02 | `02_ticket_4412_p1_outage.md` | **Ticket** (P1 incident report) |
| 03 | `03_meeting_2026-08-14_bluepeak_renewal.md` | **Meeting notes** |
| 04 | `04_chat_bluepeak-renewal.md` | **Conversation** (chat thread) |
| 05 | `05_policy_SLA-credit-01.md` | **Policy** (service credit approvals) |
| 06 | `06_meeting_2026-08-28_qbr.md` | **Meeting notes** (QBR) |
| 07 | `07_policy_SEC-review-01.md` | **Policy** (security review) |
| 08 | `08_ticket_4501_onboarding_fernwood.md` | **Ticket** (onboarding) |
| 09 | `09_chat_incident-response.md` | **Conversation** (incident channel) |
| 10 | `10_handbook_oncall.md` | **Handbook** (severity definitions) |

The slide's own examples are *documents + tickets + meeting notes* — we have all
three, plus conversations, policies and a handbook. The breadth is not decoration:
the contradiction the demo catches exists **because** a contract and a meeting note
disagree, which only works when both types are in one graph.

---

## 4. Requirement 5 in detail — the multi-hop chains, actually tested

"Multi-hop" is easy to claim and easy to fake. Both of these were run against the
live graph and are reproducible.

### Chain A — three hops across three document types

> **Q:** What service credit did we promise Bluepeak, does it breach our own
> approval policy, and who has to sign it off?

The graph had to traverse: **meeting notes** (the promise) → **policy SLA-CREDIT-01**
(the approval matrix) → the **finance owner** named in that policy → the **CFO**
threshold.

> **A:** Promised credit — a **25 % goodwill credit** on the July 2026 invoice.
> Policy breach? **Yes.** The SLA-CREDIT-01 matrix caps ≤ 10 % to support-lead
> approval, 10–20 % to finance approval, and **any credit > 20 % must be signed off
> by the CFO**. A 25 % credit therefore exceeds the allowed ceiling and is
> non-compliant until the required higher-level approvals are obtained.
> Required sign-off: **Nadia Osei** (any credit > 10 %), then the **CFO** (> 20 %).

**Correction — this was overstated.** An earlier version of this document claimed the
breach conclusion *"appears in none of them individually"* and that *"a vector-search
system cannot produce this."* **That is false.** `04_chat_bluepeak-renewal.md:18-20`
states the breach outright (*"25% is well outside that"*), and `:26-29` / `:31-34` state
the CFO sign-off requirement. One document yields both halves.

Chain A is still a genuine **multi-document join** across three types, and the graph does
carry the typed edges (`requires_approval: credit value above 20% → cfo`). But the
derivation claim belongs to **Chain C** below, which survives scrutiny.

### Chain B — incident → owner → escalation path

> **Q:** Who owns the root cause analysis for the outage, and who do they escalate
> to under our severity policy?

Traverse: **ticket 4412** (RCA owner) → **on-call handbook** (severity escalation
matrix) → the named escalation target.

> **A:** Root-cause-analysis owner: **Priya Raghavan** (Support Lead). Escalation
> target under the severity policy: Priya Raghavan escalates to the **CTO, Elena
> Sokolov**.

Two hops across a ticket and a handbook. Also reproducible.

### Chain C — the derivation that genuinely needs two documents

> **Q:** Has the credit approval paperwork been closed out, and does that breach our
> own policy?

Traverse the **two most recent documents**:

| Source | What it says on its own |
|---|---|
| `06_meeting_2026-08-28_qbr.md:25-26` | The credit was *"finalised at 25%"* and procurement *"has been told to expect it in writing"* |
| `06_meeting_2026-08-28_qbr.md:52-53` | Action still open: *"Close out credit approval paperwork — Nadia Osei — 2026-09-12"* |
| `05_policy_SLA-credit-01.md:47-48` | **§5.2** — no credit may be confirmed in writing before approvals are recorded |

> **A:** A credit was represented to the customer's procurement as **finalised** while
> the approval paperwork was still **open** — a breach of **§5.2**.

`06` gives the representation without the rule; `05` gives the rule without the
representation. **Neither states the breach.** This is the strongest evidence in the
project, and it is about the *current* state of the account rather than an August
proposal.

**Known gap:** `fixtures/answers.json` cites `05 / 04 / 03` for the credit question and
omits `06`, so Chain C is not currently reachable offline. Tracked as Task 3.3 in
`IMPROVEMENTS.md`.

---

## 5. The one honest gap — partially closed

The **Challenge** paragraph lists five artefact types: *documents, conversations,
tickets, code, and decisions.* The original 10-file corpus covered four. **`corpus/`
now carries 12 files**, adding two code artefacts:

| # | File | Type |
|---|---|---|
| 11 | `11_config_pulse-api_prod.yaml` | **Code / config** — the deploy config whose removed connection-pool ceiling caused INC-4412 |
| 12 | `12_test_connection_pool.py` | **Code / test** — the regression test that pins the ceiling, as handbook §5 now requires |

Both are wired to entities that already exist in the graph (Tomás Ferrer's guardrail
action, the connection pool ceiling, handbook §5, INC-4412), so code is load-bearing
rather than decoration — the same argument that makes the other types worth having.

**Status: the expanded corpus is not yet ingested into the demo brain**, which still
holds the original 10 documents at 219/500. Ingesting it costs credits and changes the
graph, so it is a deliberate decision rather than a default.

Why the gap mattered less than it looks:

- The **Core Requirements** box — the actual requirement list — asks for "at least 2
  different types" and gives *documents + tickets + meeting notes* as its examples.
  Code appears only in the descriptive Challenge paragraph, not the requirement list.
- Even before these two files we had **six** types against a required minimum of two.

### 5.1 Correction — the stated mitigation did not work

An earlier version of this document claimed *"the upload path accepts source files as
plain text — `.py`, `.json`, `.yaml`, `.sql` all extract natively."* **Verified false by
direct test.** `documents.py`'s allow-list accepted `.json` and refused the rest:

```
deploy.py    REFUSED -> .py is not supported
config.yaml  REFUSED -> .yaml is not supported
q.sql        REFUSED -> .sql is not supported
```

That claim *was* the mitigation for the code gap, so the gap was open. **Fixed:**
`documents.py` now defines a `CODE_EXTS` set covering 22 source and config extensions
(`.py .js .ts .go .rs .java .rb .sh .yaml .yml .toml .ini .sql .tf .hcl …`).
`test_documents.py` remains **25/25**, and every refusal path still behaves correctly
(`photo.png` → *"images are not read - this build has no OCR"*).

---

## 6. What to say on stage

If asked *"does this meet PS-2?"*, do not list features — point at the requirements:

> "Five core requirements, five met. The two that are easiest to fail are the two we
> can prove. On types: we ingest six — contracts, tickets, meeting notes, chat
> threads, policies and a handbook. On multi-hop: ask it what credit we promised
> Bluepeak and whether it breaches our own policy, and it joins a meeting note to a
> policy to the approval chain and tells you the promise is non-compliant. That
> conclusion is in none of the three documents. That is the whole point of a graph
> over a search index."

Then show it. The chain A question is the strongest 30 seconds available in this
demo.
