"""PR-6 backfill: durable brain identity from the live name-based records.

Rehearse against the lab copy first, then run on live:
    DATABASE_URL=... COGNEE_SERVICE_URL=... python3 ops/backfill.py

What it does (idempotent):
  1. one workspace per distinct org_id in brain_access (org identifiers are
     read and used, never printed)
  2. one brains row per brain_access entry: company_brain => kind=DEMO,
     READY, generation ACTIVE bound to the live tenant dataset (if present);
     anything else whose dataset is missing on the tenant => state
     DEGRADED_NOT_QUERYABLE, generation ABANDONED, ownership retained
  3. chats.brain_id backfilled ONLY where the chat's brain is a registered
     brain; everything else stays NULL and is reported unresolved_legacy
     (uploads.json stale keys are reported, never backfilled — no evidence
     of ownership or content identity)
Exits non-zero if any expected==actual reconciliation fails.
"""
from __future__ import annotations

import json
import os
import sys
import uuid

import psycopg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEMO_DATASET = os.getenv("COGNEE_DATASET", "company_brain")
REPORT: list[str] = []


def note(s: str) -> None:
    REPORT.append(s)
    print(s)


def q(cur, sql: str, args=()):
    cur.execute(sql, args)
    try:
        return cur.fetchall()
    except psycopg.ProgrammingError:
        return []  # INSERT/UPDATE without RETURNING


def main() -> None:
    url = os.environ["DATABASE_URL"]
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        before = {t: q(cur, f"select count(*) from {t}")[0][0]
                  for t in ("workspaces", "brains", "brain_generations",
                            "brain_access", "chats")}
        note(f"before: {before}")

        # --- live tenant datasets (name -> id) ---------------------------
        import cognee_cloud
        datasets = {d.get("name"): d.get("id") for d in cognee_cloud.datasets()}
        note(f"tenant datasets: {sorted(k for k in datasets if k)}")

        # --- 1. workspaces (one per distinct org; ids never printed) ------
        orgs = [r[0] for r in q(cur, "select distinct org_id from brain_access where org_id is not null")]
        org_ws = {}
        for org in orgs:
            ws_id = str(uuid.uuid4())
            q(cur, """insert into workspaces (id, clerk_org_id)
                      values (%s, %s) on conflict (clerk_org_id) do nothing""",
              (ws_id, org))
            row = q(cur, "select id from workspaces where clerk_org_id = %s", (org,))
            org_ws[org] = row[0][0]
        note(f"workspaces ensured: {len(org_ws)} org workspace(s)")

        # --- 2. brains + generations from brain_access ---------------------
        created_brains = 0
        for brain, org_id, created_by, is_shared in q(
                cur, "select brain, org_id, created_by, is_shared from brain_access order by brain"):
            ws = org_ws.get(org_id)
            if ws is None:  # defensive: should not happen
                note(f"SKIP {brain}: org row has no workspace (report to operator)")
                continue
            existing = q(cur, "select id from brains where workspace_id=%s and slug=%s", (ws, brain))
            if existing:
                note(f"SKIP {brain}: brains row already exists")
                continue
            brain_id = str(uuid.uuid4())
            is_demo = brain == DEMO_DATASET
            dataset_id = datasets.get(brain)
            state = "READY" if dataset_id else "DEGRADED_NOT_QUERYABLE"
            gen_state = "ACTIVE" if dataset_id else "ABANDONED"
            q(cur, """insert into brains (id, workspace_id, slug, display_name, owner_user_id,
                                              visibility, kind, storage_mode, state)
                      values (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
              (brain_id, ws, brain, brain, created_by,
               "DEMO" if is_demo else "PRIVATE",
               "DEMO" if is_demo else "UPLOAD",
               "VERSIONED", state))
            gen_id = str(uuid.uuid4())
            q(cur, """insert into brain_generations (id, brain_id, workspace_id, generation_number,
                                        backend_dataset_name, backend_dataset_id, state,
                                        publication_mode, inventory_verified_at)
                      values (%s,%s,%s,1,%s,%s,%s,'VERSIONED',
                              case when %s then now() else null end)""",
              (gen_id, brain_id, ws, brain, dataset_id, gen_state, dataset_id is not None))
            if dataset_id:
                q(cur, """update brains set active_generation_id=%s
                          where id=%s and workspace_id=%s""", (gen_id, brain_id, ws))
            created_brains += 1
            note(f"brain {brain}: state={state} dataset={'live' if dataset_id else 'MISSING on tenant'}")
        note(f"brains created: {created_brains}")

        # --- 3. chats.brain_id (only where provable) ------------------------
        unresolved = []
        for chat_id, brain in q(cur, "select id, brain from chats where brain_id is null and brain is not null"):
            row = q(cur, """select b.id from brains b where b.slug=%s""", (brain,))
            if row:
                q(cur, "update chats set brain_id=%s where id=%s", (row[0][0], chat_id))
            else:
                unresolved.append((chat_id, brain))
        note(f"chats linked: matched a registered brain; unresolved_legacy chats: "
             f"{len(unresolved)} -> {[b for _, b in unresolved]}")

        # --- 4. uploads.json stale keys: report only ------------------------
        try:
            manifest = json.load(open("cognee_oss_state/uploads.json"))
            stale = [k for k in manifest if k not in datasets and k != "_collisions"]
            note(f"manifest keys: {len(manifest)}; stale (dataset absent, NOT backfilled): {sorted(stale)}")
        except Exception as exc:  # noqa: BLE001
            note(f"manifest unreadable: {exc}")

        # --- reconciliation -------------------------------------------------
        after = {t: q(cur, f"select count(*) from {t}")[0][0]
                 for t in ("workspaces", "brains", "brain_generations", "brain_access", "chats")}
        note(f"after: {after}")
        assert after["brain_access"] == before["brain_access"], "brain_access changed!"
        assert after["chats"] == before["chats"], "chat count changed!"
        assert after["brains"] - before["brains"] == len(
            q(cur, "select 1 from brain_access")), "brains rows != brain_access rows"
        assert after["brain_generations"] - before["brain_generations"] == created_brains
        linked = q(cur, "select count(*) from chats where brain_id is not null")[0][0]
        note(f"chats with brain_id set: {linked}")
        conn.commit()
    print("\nBACKFILL OK")


if __name__ == "__main__":
    main()
