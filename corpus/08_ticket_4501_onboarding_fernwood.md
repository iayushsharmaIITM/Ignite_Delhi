# Ticket 4501 — Onboarding: Fernwood Grocers

**Ticket:** 4501
**Severity:** P3
**Customer:** Fernwood Grocers
**Opened:** 2026-07-22 10:04 UTC
**Resolved:** 2026-07-24 16:20 UTC
**Owner:** Priya Raghavan (Support Lead)
**Assignee:** Jonas Beck (Solutions Engineering)

---

## Summary

Fernwood Grocers (new customer, 62 stores, signed 2026-07-01) required assistance
completing their initial data onboarding for the Kestrel Pulse platform.

## Detail

Fernwood's POS export produced timestamps in local store time with no timezone offset.
The ingestion pipeline interpreted these as UTC, shifting their sell-through reporting
by up to 14 hours depending on store location.

## Resolution

Solutions Engineering provided a revised export configuration specifying ISO-8601
timestamps with explicit offsets. Fernwood re-exported and the backlog was reprocessed.

## Follow-up

- [x] Export template updated in the onboarding documentation
- [x] Timezone validation added to the ingestion pre-flight check
- [ ] Add a warning to the ingestion UI when a source has no timezone metadata — backlog

## Notes

This was a **P3** — no production impact for any existing customer, and Fernwood's
go-live date was not affected. Handled within business hours; no escalation required and
no service credit applicable.

**Contract:** MSA-2026-0077 (Fernwood Grocers)
