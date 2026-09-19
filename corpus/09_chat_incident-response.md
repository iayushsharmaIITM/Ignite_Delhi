# #incident-response — chat thread

**Channel:** #incident-response
**Date:** 9 July 2026

---

**pagerduty-bot** 02:14
:rotating_light: ALERT — pulse-api error rate 41% (threshold 5%). Paging on-call.
Ticket 4412 auto-created.

**tomas.ferrer** 02:16
Ack. I'm on it. Looking at the error rate graph now — it's everything, not just one
endpoint. Dashboard is 503ing too.

**tomas.ferrer** 02:19
This looks like connection exhaustion. Pool metrics are pegged. Checking what shipped
in the last hour.

**priya.raghavan** 02:23
Joining. I'm declaring this **P1** — full Pulse unavailability, multiple tenants
affected. Per the handbook that's P1 by definition, and I'm not waiting to confirm
scope.

**tomas.ferrer** 02:26
Confirmed. `pulse-api@v4.18.2` went out at 02:07. The diff drops an explicit pool
ceiling from the DB config. That's almost certainly it.

**priya.raghavan** 02:31
Bluepeak's VP Ops (Dana Whitfield) has emailed the support inbox already. They're inside
their Back-to-School promo window. I'll take customer comms.

**elena.sokolov** 02:33
Acknowledged. Rollback is pre-authorised for a P1 — don't wait for me. Do it now.

**tomas.ferrer** 02:52
Rollback started.

**tomas.ferrer** 03:01
Service restored. Error rate at baseline. Total unavailability: 47 minutes. Ingested
events are queued and draining now.

**elena.sokolov** 03:08
Good work, both. Priya — I want a postmortem and a customer-facing RCA pack. Tomás —
I want a guardrail so a config push can't remove that ceiling again. Both this week.

**priya.raghavan** 03:11
Will do. Note for the record: 47 minutes in a single month will put any large customer
under a 99.9% monthly commitment. Expect a service credit conversation.

**elena.sokolov** 03:14
Understood. Route that through the credit policy, not through the account team directly.

---

**Thread pinned** — postmortem owner: Priya Raghavan
