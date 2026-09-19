# On-Call Handbook — Severity Definitions and Escalation

**Owner:** Elena Sokolov (CTO)
**Applies to:** Support, SRE, and Engineering
**Version:** 6.2

---

## 1. Severity definitions

| Severity | Definition | Acknowledgement target | Comms cadence |
|---|---|---|---|
| **P1** | Full loss of the Pulse dashboard or ingestion pipelines, affecting **one or more** customers. Includes data loss or data corruption. | 15 minutes, 24×7 | Every 30 minutes to affected customers |
| **P2** | Significant degradation, or a single customer fully affected while others are unaffected. | 60 minutes, business hours | Every 4 hours |
| **P3** | Minor issue, cosmetic defect, or a request that can be scheduled. | 1 business day | Weekly update |

**A P1 is declared by severity of customer impact, not by confirmed root cause.** If the
impact is unclear and the blast radius is potentially broad, declare P1 and downgrade
later. Downgrading is cheap; a late declaration is not.

## 2. Escalation path

```
On-call engineer (ack 15 min)
      │  no ack, or P1 not contained within 30 min
      ▼
Support Lead (Priya Raghavan)
      │  P1 exceeding 60 min, or any data loss
      ▼
CTO (Elena Sokolov)
      │  customer-facing commercial impact
      ▼
Account Executive + Finance
```

## 3. Authority during a P1

- Rollback of the most recent production deploy is **pre-authorised** for the on-call
  engineer. Do not wait for approval.
- The Support Lead owns all customer communication during an incident.
- The on-call engineer owns technical remediation and must not be pulled into customer
  comms.

## 4. Post-incident requirements

| Requirement | Owner | Deadline |
|---|---|---|
| Internal postmortem | Incident owner | 5 business days |
| Customer-facing RCA (for P1) | Support Lead | 10 business days |
| Guardrail / regression test | Owning engineer | Next sprint |
| Service credit assessment | Finance | With the monthly close |

**Note:** A service credit assessment is **mandatory** for every P1. Do not leave it to
the account team to raise.

## 5. Configuration change safety

Configuration pushes follow the same change-control path as code deploys. Any change to
database connection settings, rate limits, or resource ceilings requires a peer review
and a regression test that pins the previous value.

This section was added following INC-4412.
