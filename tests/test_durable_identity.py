"""Citation identity: which document VERSION does this citation actually point at?

Run standalone (no database, no provider, no network — CI fast lane safe):

    python3 tests/test_durable_identity.py

Prints one PASS/FAIL line per check and exits non-zero if any failed.

Two defects, both in the durable provenance path a v2-created brain relies on:

  * `_durable_reference` selected `limit 1` with no `ORDER BY`, matching on
    `(b.slug = dataset OR g.backend_dataset_name = dataset) AND gd.backend_data_id = id`.
    `backend_data_id` is a CONTENT identifier, so the same file inside two brains, or
    inside two generations of one brain, matches twice — and the citation then named
    whichever row the planner reached first. Non-deterministic, and quiet about it.
  * `durable_source` read the newest `document_versions` row for a slug+filename
    (`order by dv.created_at desc limit 1`). An answer produced from version A keeps
    opening version B after someone re-uploads the same filename. The citation is not
    wrong about the text it quotes; it is wrong about which document it says the quote
    came from.

The fixes are additive: a citation now carries `document_version_id`, `/api/source`
accepts it, and only when it is present is the exact version read. With no id the old
behaviour is kept, because every chat saved before this change has none.

The database seam under test is `citations._rows` — one read-only query helper both
lookups go through, replaced here by a fake so ambiguity can be proven with no server.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PROVIDER"] = "mock"
os.environ["AUTH_MODE"] = "off"

import citations  # noqa: E402

FAILS = []
CHECKS = 0


def check(name, ok, detail=""):
    global CHECKS
    CHECKS += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else '  <- ' + detail}")
    if not ok:
        FAILS.append(name)


def row(version="v-1", generation="g-1", filename="policy.md", text="Version one text."):
    return {"document_version_id": version, "generation_id": generation,
            "active_generation_id": None,
            "filename": filename, "exact_extracted_text": text}


QUERIES = []


def fake_rows(rows):
    """Replace the DB seam: record the SQL, answer with fixed rows."""
    def _inner(sql, params):
        QUERIES.append(sql)
        return [dict(r) for r in rows]
    return _inner


if not hasattr(citations, "_rows"):
    check("citations._rows exists as the durable-query seam", False,
          "the seam these checks drive is not in the module yet — every check below is "
          "therefore unproven, not passing")
else:
    real_rows = citations._rows

    # --- 1. one matching row: resolved, and carrying its version id -----------------
    citations._rows = fake_rows([row()])
    got = citations._durable_reference("acme", "deadbeef")
    check("a single durable match resolves", bool(got) and got.get("source") == "policy.md",
          f"got {got}")
    check("and the citation carries the document_version_id",
          bool(got) and got.get("document_version_id") == "v-1",
          f"got {got}")

    # --- 2. two different versions for one data id: unknown, never a guess ---------
    citations._rows = fake_rows([row(version="v-1", generation="g-1"),
                                 row(version="v-2", generation="g-2",
                                     filename="other.md", text="Different text.")])
    got = citations._durable_reference("acme", "deadbeef")
    check("two candidate versions resolve to NOTHING rather than an arbitrary one",
          got is None, f"returned {got}")
    sql = QUERIES[-1]
    check("the lookup asks for more than one candidate (it cannot detect a clash at limit 1)",
          "limit 1" not in sql.lower(), "still `limit 1`")
    check("and it orders the rows, so the result cannot depend on the plan",
          "order by" in sql.lower(), "no ORDER BY")

    # --- 3. duplicate join rows for the SAME version are not a clash ---------------
    citations._rows = fake_rows([row(version="v-1", generation="g-1"),
                                 row(version="v-1", generation="g-1")])
    got = citations._durable_reference("acme", "deadbeef")
    check("two rows that are the same version are not called ambiguous",
          bool(got) and got.get("document_version_id") == "v-1", f"got {got}")

    # --- 4. no rows at all is still just "not durable" -----------------------------
    citations._rows = fake_rows([])
    check("no durable row means None, not an error",
          citations._durable_reference("acme", "deadbeef") is None)

    # --- 4b. a rebuilt brain legitimately holds the same content twice -------------
    # backend_data_id is content, and the unique index is per GENERATION, so after a
    # REBUILD publishes, one brain can hold the same document in its active generation
    # and in the retired one. That is not ambiguity — the active generation is the
    # answer. Refusing everything that matched twice would silently strip durable
    # provenance from every rebuilt brain, which is exactly the regression S6 would
    # otherwise introduce.
    def grow(version, generation, active, filename="policy.md", text="t"):
        return {"document_version_id": version, "generation_id": generation,
                "active_generation_id": active, "filename": filename,
                "exact_extracted_text": text}

    citations._rows = fake_rows([grow("v-9", "g-new", "g-new", filename="current.md"),
                                 grow("v-1", "g-old", "g-new", filename="retired.md")])
    got = citations._durable_reference("acme", "deadbeef")
    check("the same content in the active generation and a retired one resolves to the active",
          bool(got) and got.get("document_version_id") == "v-9", f"got {got}")

    citations._rows = fake_rows([grow("v-1", "g-old", "g-new", filename="one.md"),
                                 grow("v-2", "g-older", "g-new", filename="two.md")])
    got = citations._durable_reference("acme", "deadbeef")
    check("and two candidates inside the SAME active generation stay ambiguous",
          got is None, f"got {got}")

    citations._rows = fake_rows([grow("v-1", "g-1", None), grow("v-2", "g-2", None)])
    check("a brain with no active generation at all keeps the old, stricter rule",
          citations._durable_reference("acme", "deadbeef") is None)

    # --- 5. durable_source: exact version when an id is given ----------------------
    citations._rows = fake_rows([row(version="v-1", text="Version one text.")])
    got = citations.durable_source("acme", "policy.md", "v-1")
    check("a citation with a version id reads exactly that version",
          got == "Version one text.", f"got {got!r}")
    check("and the query filters on the id it was given",
          "dv.id" in QUERIES[-1] and QUERIES[-1].count("%s") >= 3,
          "the version id never reached the SQL")

    # --- 6. durable_source without an id behaves as it always did ------------------
    citations._rows = fake_rows([row(version="v-2", text="Newest text.")])
    got = citations.durable_source("acme", "policy.md")
    check("no version id keeps today's newest-wins lookup", got == "Newest text.",
          f"got {got!r}")
    check("which is still newest-first and single-row",
          "order by" in QUERIES[-1].lower() and "limit 1" in QUERIES[-1].lower(),
          "the legacy path changed shape")

    # --- 7. enrich: the version id travels with the citation -----------------------
    citations._rows = fake_rows([row(version="v-9", filename="policy.md",
                                     text="Nine text.")])
    citations._id_cache.clear()
    # An unresolvable dataset on purpose: cognee_cloud.resolve_id fails, the tenant
    # branch stands down, and the ONLY way this reference can be named at all is the
    # durable lookup — which is exactly the path that must carry the version id.
    items = citations.enrich(
        ["chunk 1 of document text_x (data_id: deadbeef, chunk_id: 1)"],
        "acme-dataset-that-does-not-exist")
    check("enrich passes document_version_id through to the citation payload",
          any(i.get("document_version_id") == "v-9" for i in items),
          f"payload is {items}")
    citations._id_cache.clear()

    citations._rows = real_rows

print("DURABLE CITATION IDENTITY (a version id or nothing):", "FAIL" if FAILS else "PASS")
if FAILS:
    print(f"  {len(FAILS)} of {CHECKS} checks failed: {', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
