# Reconciliation inventory (A8) — 2026-09-30T21:10Z

Four record systems, one brain namespace. Today's live state:

| Dataset (Cognee tenant) | brain_access row | uploads.json key | chats.brain |
|---|---|---|---|
| company_brain | yes | no (by design: demo cites corpus/) | none |
| acme_isolated | yes | no | none |
| hghi | no | yes (1) | 1 chat |
| kestrel_full | no | no | 1 chat |
| 100_people, new_100_people, acme_industrial, appendtest1, deltest1, namedcite1, paytm_ai, ux_scratch_del, _collisions | no | yes (11 entries total) | none |

## Findings
1. Tenant holds exactly 1 dataset: company_brain. Every other name in every
   other system refers to a dataset that no longer exists on the tenant.
2. acme_isolated: ownership row exists, dataset gone → in Clerk mode this
   brain passes brain_allowed (row present) and then fails at recall
   (dataset missing) — an authorizable-but-dead brain (issue #3 class).
3. uploads.json: 10 keys / 13 entries, ALL for deleted datasets — stale
   manifest (never cleaned on delete; issue #12 class). company_brain
   correctly absent (demo brain cites corpus/ from disk).
4. chats reference hghi and kestrel_full — both nonexistent on the tenant.
   Asking those chats today fails at recall (brain_access has no row →
   403 'Unknown brain' in Clerk mode first).

## Disposition (NO repair performed — backfill phase, pending approval)
- All stale keys are test/scratch artifacts (names: 100_people, new_100_people,
  acme_industrial, appendtest1, deltest1, namedcite1, paytm_ai, ux_scratch_del,
  _collisions). Recommended later: prune manifest keys with no live dataset +
  no brain row; quarantine chats with no live brain (visible or tombstoned).
- company_brain graph lives in Postgres graph_* (93 nodes / 161 edges) —
  intact and consistent with a working known-answer ask today.
