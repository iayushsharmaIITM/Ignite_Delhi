# INC-4412 — Priority 1 Incident Report

**Ticket:** 4412
**Severity:** P1
**Customer:** Bluepeak Retail Holdings
**Opened:** 2026-07-09 02:14 UTC
**Resolved:** 2026-07-09 03:01 UTC
**Duration:** 47 minutes
**Owner:** Priya Raghavan (Support Lead)
**On-call engineer:** Tomás Ferrer (SRE)

---

## Summary

Kestrel Pulse dashboard and ingestion pipelines were unavailable for all Bluepeak
tenants for 47 minutes. During the incident, ingested point-of-sale events queued but
were not processed; the dashboard returned HTTP 503 for all requests.

## Customer impact

The outage fell inside **Bluepeak's "Back-to-School" promotional window (6–20 July)**,
the highest-volume trading period of their retail calendar. Bluepeak's operations team
could not see store-level sell-through for the duration.

## Timeline (UTC)

| Time | Event |
|---|---|
| 02:07 | Config push `pulse-api@v4.18.2` deployed to production |
| 02:14 | Monitoring fires: dashboard error rate > 40%. Ticket 4412 auto-created |
| 02:16 | Tomás Ferrer paged, acknowledges |
| 02:23 | Priya Raghavan joins, declared P1 |
| 02:31 | Dana Whitfield (Bluepeak VP Ops) emails the shared support inbox |
| 02:44 | Root cause identified |
| 02:52 | Rollback of `pulse-api@v4.18.2` begins |
| 03:01 | Service fully restored, error rate back to baseline |
| 03:40 | Backlog of queued POS events fully drained |

## Root cause

`pulse-api@v4.18.2` removed an explicit database connection pool ceiling as part of an
unrelated performance change. Under Bluepeak's promotion-window traffic the pool grew
unbounded, exhausting available connections and starving the ingestion workers.

## Monthly uptime impact

July 2026 measured uptime: **99.89%** — below the 99.9% commitment in MSA-2025-0114 §4.1.

## Follow-up actions

- [x] Rollback completed
- [x] Connection pool ceiling restored and pinned by test
- [ ] Postmortem document circulated — owner: Priya Raghavan
- [ ] Root cause analysis pack prepared for Bluepeak — owner: Priya Raghavan
- [ ] Deploy guardrail added to config pipeline — owner: Tomás Ferrer

**Related:** MSA-2025-0114 §4, policy SLA-CREDIT-01
