# Policy SEC-REVIEW-01 — Annual Security Review

**Owner:** Elena Sokolov (CTO)
**Applies to:** All production systems handling customer data
**Last reviewed:** 2026-02-18

---

## 1. Certification

Kestrel Analytics maintains **SOC 2 Type II** certification. The report is renewed
annually and covers security, availability, and confidentiality trust principles.

Several enterprise contracts — including MSA-2025-0114 §6.1 — require that the current
report be made available to the customer on request.

## 2. Penetration testing

An external penetration test is commissioned annually. Findings are triaged into the
engineering backlog within ten business days of report delivery. Any critical finding
carries a remediation deadline of thirty days.

## 3. Access control

Production access requires hardware-key MFA. Standing production access is granted to
the SRE team only; engineers request just-in-time access for a maximum window of eight
hours.

## 4. Sub-processors

Customers must be notified **thirty (30) days** before any new sub-processor begins
processing their data. The sub-processor register is maintained by the security team and
published to the customer trust portal.

## 5. Data retention

Customer data is retained for the duration of the contract plus thirty days, after which
it is destroyed according to the documented destruction procedure.

## 6. Incident notification

A confirmed breach of customer data requires notification to affected customers within
**seventy-two hours** of confirmation. Notification is owned by the CTO, not by the
account team.

## 7. Vendor questionnaires

Completed security questionnaires are valid for twelve months. Sales may not represent
Kestrel's security posture beyond what is documented in the current SOC 2 report or a
completed questionnaire.
