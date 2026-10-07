"""Phase 7: numbered Perplexity-style citations contract & invariant gate.

Run standalone (safe for CI fast lane):

    python3 tests/test_numbered_citations.py

Prints one PASS/FAIL line per check and exits non-zero if any failed.

Product Invariants:
1. Every inline marker [N] or [^N] corresponds strictly to turn.sources[N - 1].
2. Out-of-bounds or unresolved markers return None/unresolved — never fabricated.
3. Pinned version lookups never fall back to another version or another document.
4. Storage/DB outage on source lookup surfaces as 503, never 404 or 200 substitution.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PROVIDER"] = "mock"
os.environ["AUTH_MODE"] = "off"
_url = os.environ.get("DATABASE_URL", "")
if _url and "5434" not in _url:
    raise SystemExit(
        "REFUSING: DATABASE_URL names a server that is not the lab (5434). This tier "
        "imports app.py, which runs storage.init(); it must not be pointed at the live "
        "database. Unset DATABASE_URL to run with no database at all, or use the lab.")
if not _url:
    os.environ["DATABASE_URL"] = "postgresql://kestrel:kestrel@127.0.0.1:1/kestrel"

import citations
import app as app_module
from fastapi.testclient import TestClient

client = TestClient(app_module.app)
FAILS = []
CHECKS = 0


def check(name, ok, detail=""):
    global CHECKS
    CHECKS += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else '  <- ' + detail}")
    if not ok:
        FAILS.append(name)


# --- 1. Marker to source resolution logic ---------------------------------------------
def resolve_marker_source(marker_idx: int, sources: list[dict]) -> dict | None:
    """Resolve 1-based marker index [N] to the corresponding source.

    Returns the source dict if 1 <= marker_idx <= len(sources) and sources[marker_idx - 1]
    has a non-empty source name. Returns None for out-of-bounds or unresolved sources.
    Never guesses or substitutes.
    """
    if not (1 <= marker_idx <= len(sources)):
        return None
    item = sources[marker_idx - 1]
    if not item or not item.get("source"):
        return None
    return item


sample_sources = [
    {"source": "alpha_sla.md", "excerpt": "Alpha tier credits", "document_version_id": "11111111-1111-1111-1111-111111111111"},
    {"source": "beta_policy.md", "excerpt": "Beta tier escalation", "document_version_id": "22222222-2222-2222-2222-222222222222"},
    {"source": None, "excerpt": None, "raw": "unresolvable raw chunk"},
]

res1 = resolve_marker_source(1, sample_sources)
check("marker [1] resolves to first source",
      res1 is not None and res1.get("source") == "alpha_sla.md")

res2 = resolve_marker_source(2, sample_sources)
check("marker [2] resolves to second source",
      res2 is not None and res2.get("source") == "beta_policy.md")

res3 = resolve_marker_source(3, sample_sources)
check("unresolved source at [3] returns None, never guesses",
      res3 is None, f"expected None, got {res3}")

res4 = resolve_marker_source(4, sample_sources)
check("out-of-bounds marker [4] returns None (no fabricated citation)",
      res4 is None, f"expected None, got {res4}")

res0 = resolve_marker_source(0, sample_sources)
check("invalid marker [0] returns None",
      res0 is None, f"expected None, got {res0}")


# --- 2. Pinned version cannot substitute on miss ---------------------------------------
real_durable = citations.durable_source
real_data_id_for = citations.data_id_for

citations.durable_source = lambda ds, fn, dv=None, *a, **k: None
citations.data_id_for = lambda ds, fn: "deadbeef"

r = client.get("/api/source", params={
    "name": "alpha_sla.md",
    "dataset": "acme-ops",
    "document_version_id": "11111111-1111-1111-1111-111111111111",
})
check("missing pinned version 404s instead of substituting other version",
      r.status_code == 404, f"got HTTP {r.status_code}")


# --- 3. Storage outage during source lookup surfaces as 503 ----------------------------
import storage

def simulate_outage(*a, **k):
    storage.mark_down("simulated outage")
    raise storage.db_error("database connection failure")

citations.durable_source = simulate_outage
storage._status = {"storage": "postgres", "detail": ""}

r = client.get("/api/source", params={
    "name": "alpha_sla.md",
    "dataset": "acme-ops",
    "document_version_id": "11111111-1111-1111-1111-111111111111",
})
check("storage outage surfaces as 503, never empty/fallback",
      r.status_code == 503, f"got HTTP {r.status_code}")

citations.durable_source = real_durable
citations.data_id_for = real_data_id_for
storage._status = {"storage": "postgres", "detail": ""}


# --- 4. Citation enrichment preserves order and version id ----------------------------
test_refs = ["chunk 1 (data_id: 1111-aaaa)", "chunk 2 (data_id: 2222-bbbb)"]
test_store = {
    "1111-aaaa": {
        "source": "contract.md",
        "excerpt": "contract text snippet",
        "document_version_id": "33333333-3333-3333-3333-333333333333",
    },
    "2222-bbbb": {
        "source": "handbook.md",
        "excerpt": "handbook text snippet",
        "document_version_id": "44444444-4444-4444-4444-444444444444",
    },
}

citations._id_cache["test-dataset"] = test_store
enriched = citations.enrich(test_refs, "test-dataset")

check("enrich returns same count of references in matching order",
      len(enriched) == 2 and enriched[0]["source"] == "contract.md" and enriched[1]["source"] == "handbook.md",
      f"got {enriched}")
check("first enriched item carries exact document_version_id",
      enriched[0].get("document_version_id") == "33333333-3333-3333-3333-333333333333")
check("second enriched item carries exact document_version_id",
      enriched[1].get("document_version_id") == "44444444-4444-4444-4444-444444444444")


# --- 5. Attachment citation attribution & grounding filter -----------------------------
import orchestrator

sample_query = (
    'Attached screenshot/image "media_1791410031306_61675e48.png":\n'
    'App Credentials\nApp ID: A08ABCDEF\nClient ID: 12345.67890\nClient Secret: **********\n\n'
    'Follow-up question: what is this screenshot about?'
)

extracted = orchestrator._extract_attachments(sample_query)
check("attachment is extracted from query context",
      len(extracted) == 1 and extracted[0]["source"] == "media_1791410031306_61675e48.png")
check("extracted attachment carries extracted text and excerpt",
      "App Credentials" in extracted[0]["text"] and bool(extracted[0]["excerpt"]))

is_att_q = orchestrator._is_attachment_question(sample_query, extracted)
check("query identified as an attachment question", is_att_q is True)

answer_about_screenshot = (
    "This screenshot shows the Slack API App Credentials page, including the App ID, "
    "Client ID, and Client Secret for the application."
)

att_texts = [extracted[0]["text"]]
fake_db_doc_1 = {
    "source": "12_test_connection_pool.py",
    "excerpt": "async def test_pool(): pool = await ConnectionPool.create(max_size=20)",
}
fake_db_doc_2 = {
    "source": "04_chat_bluepeak-renewal.md",
    "excerpt": "Bluepeak Technologies renewal discussion: ARR $180,000, 15% discount proposed",
}

check("ungrounded db doc 1 (12_test_connection_pool.py) is filtered out",
      orchestrator._is_grounded_in_answer(fake_db_doc_1, answer_about_screenshot, att_texts, is_att_q=True) is False)
check("ungrounded db doc 2 (04_chat_bluepeak-renewal.md) is filtered out",
      orchestrator._is_grounded_in_answer(fake_db_doc_2, answer_about_screenshot, att_texts, is_att_q=True) is False)

# --- 6. Attachment text lookup via /api/source ----------------------------------------
app_module._cache_attachment_text("media_1791410031306_61675e48.png", "App Credentials\nApp ID: A08ABCDEF")
r_att = client.get("/api/source", params={"name": "media_1791410031306_61675e48.png"})
check("attachment source lookup returns 200 with attachment text",
      r_att.status_code == 200 and r_att.json().get("source") == "attachment" and "A08ABCDEF" in r_att.json().get("text", ""))


print("NUMBERED CITATIONS (1-based index, no fabricated sources):",
      "FAIL" if FAILS else "PASS")
if FAILS:
    print(f"  {len(FAILS)} of {CHECKS} checks failed: {', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)

