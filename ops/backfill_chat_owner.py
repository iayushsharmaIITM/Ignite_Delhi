"""Stamp the server-side owner onto chats that predate ownership (SEC-5 tail).

    python3 ops/backfill_chat_owner.py            # dry run: report only
    python3 ops/backfill_chat_owner.py --apply    # write

Why a tool and not a one-line UPDATE: the rows in question were written before
P3 stamped ownership server-side, and some were written by the verification
battery itself while it still ran with AUTH_MODE=off. `storage._owner_clause`
currently hands every `(org_id IS NULL AND created_by IS NULL)` row to EVERY
authenticated user, because the demo history depends on it. That grandfathering
can only be removed once those rows know whose they are - and the answer has to
come from evidence, not from a guess: each chat's `brain` is looked up in
`brain_access`, and a chat whose brain has no recorded owner is LEFT ALONE and
reported, because inventing an owner would be worse than admitting the gap.

Idempotent: rows that already carry an org or a creator are not touched.
Reversible: --apply prints every (chat id, previous org, previous creator) pair
to /tmp/kestrel_backfill_chat_owner.json, so any single row can be set back.
"""
from __future__ import annotations

import json
import os
import sys
import time

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
URL = os.getenv("DATABASE_URL", "")
if not URL:
    sys.exit("DATABASE_URL is required — point it at the database you intend to "
             "check (lab 5434 first, then live).")

APPLY = "--apply" in sys.argv
REPORT_PATH = "/tmp/kestrel_backfill_chat_owner.json"

# A chat is only stampable when its brain has exactly one unambiguous owner:
# an org, a creator, or both. Anything else stays NULL and is reported.
SQL = """
SELECT c.id, c.brain, c.org_id AS cur_org, c.created_by AS cur_creator,
       (SELECT count(*) FROM turns t WHERE t.chat_id = c.id) AS turns,
       b.org_id AS brain_org, b.created_by AS brain_creator, b.status
FROM chats c
LEFT JOIN brain_access b ON b.brain = c.brain
WHERE c.org_id IS NULL AND c.created_by IS NULL
ORDER BY c.brain, c.updated
"""

with psycopg.connect(URL, row_factory=dict_row) as conn, conn.cursor() as cur:
    rows = cur.execute(SQL).fetchall()

stampable, unresolved, ambiguous = [], [], []
for r in rows:
    if r["brain_org"] is None and r["brain_creator"] is None:
        # Either no brain_access row at all, or a row that records no owner
        # (the shared demo brain). Guessing would attribute someone else's
        # history, so these are reported and left NULL.
        unresolved.append(r)
        continue
    if r["status"] == "creating":
        # A claim, not a brain: its owner is provisional until the dataset is
        # confirmed, so history filed under it cannot be credited yet.
        ambiguous.append(r)
        continue
    stampable.append(r)

print(f"chats with no owner: {len(rows)}   "
      f"stampable: {len(stampable)}   unresolved brain: {len(unresolved)}   "
      f"claimed-not-ready: {len(ambiguous)}")

for label, group in (("STAMP", stampable), ("HOLD (brain has no owner)", unresolved),
                     ("HOLD (brain is a live claim)", ambiguous)):
    for r in group:
        owner = r["brain_org"] or "(creator only)"
        print(f"  {label:26} {r['id'][:28]:28} brain={r['brain'] or '-':18} "
              f"turns={r['turns']:3} -> {owner}")

if not APPLY:
    print("\ndry run — nothing written. Re-run with --apply to stamp the "
          f"{len(stampable)} STAMP rows.")
    sys.exit(0)

if not stampable:
    print("\nnothing to do.")
    sys.exit(0)

undo = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "database": URL.split("@")[-1],
        "rows": [{"id": r["id"], "prev_org": None, "prev_creator": None} for r in stampable]}
with psycopg.connect(URL, autocommit=False) as conn, conn.cursor() as cur:
    for r in stampable:
        cur.execute(
            """UPDATE chats SET org_id = COALESCE(org_id, %s),
                                 created_by = COALESCE(created_by, %s)
                WHERE id = %s AND org_id IS NULL AND created_by IS NULL""",
            (r["brain_org"], r["brain_creator"], r["id"]),
        )
    conn.commit()
    left = cur.execute(
        "SELECT count(*) AS n FROM chats WHERE org_id IS NULL AND created_by IS NULL").fetchone()["n"]

with open(REPORT_PATH, "w") as fh:
    json.dump(undo, fh, indent=1)
print(f"\nstamped {len(stampable)} chats in ONE transaction; {left} still "
      f"unowned (by design).")
print(f"previous values recorded in {REPORT_PATH} for reversal.")
