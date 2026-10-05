"""Ambiguous fingerprints name nothing. A guessed filename is a fabricated citation.

Run standalone (no database, no provider, no network, no browser — CI fast lane safe):

    python3 tests/test_citation_collisions.py

Prints one PASS/FAIL line per check and exits non-zero if any failed.

Why this file exists. A citation's filename is recovered by matching the first 120
normalised characters of a document's raw text against local copies (`_fingerprint`).
That prefix is not unique: two documents that open the same way collide. Three defects
fell out of that, all reproduced against the code as it was written:

  * `corpus/` was mapped last-writer-wins, so of two colliding files the alphabetically
    later one silently owned both citations — `06_policy_B.md` answered for `05_policy_A.md`.
  * `record_upload` records the collision in uploads.json under `_collisions` and keeps the
    first name, and NOTHING has ever read that table back (A-57). The manifest therefore
    still resolved a known-ambiguous fingerprint to one of its two owners.
  * An empty (or whitespace-only) corpus file fingerprints to "", which is exactly what a
    FAILED raw fetch fingerprints to — so every unfetchable document borrowed that file's
    name. `fetch_raw` returns None on any error, so this was one `touch` from live.

The product invariant is that a citation is never invented, so an ambiguous fingerprint
resolves to no filename at all. The honest "unresolved" chip is a worse-looking UI and a
better product.

What is deliberately NOT ambiguous: when the same content is in `corpus/` AND in a
tenant's own uploads, the upload's filename wins. The tenant calls it what they uploaded
it as; the demo filename would be the wrong label. Check 4 holds that.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import citations  # noqa: E402

FAILS = []
CHECKS = 0


def check(name, ok, detail=""):
    global CHECKS
    CHECKS += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else '  <- ' + detail}")
    if not ok:
        FAILS.append(name)


# Long enough that the two documents share their entire fingerprint and differ only
# past it — the collision the real corpus can produce and the reader cannot see.
PREFIX = "policy sla-credit-01. this document defines service credit eligibility for " * 2
TEXT_A = PREFIX + "alpha tier customers only."
TEXT_B = PREFIX + "beta tier customers only."
TEXT_UNIQUE = "an entirely different opening, about on-call rotations and paging thresholds."
COLLIDED = citations._fingerprint(TEXT_A)
assert COLLIDED == citations._fingerprint(TEXT_B), "fixture must share a fingerprint"
assert len(PREFIX) >= 120, "the collision has to be inside the fingerprint window"

REAL_CORPUS, REAL_UPLOADS = citations.CORPUS, citations.UPLOADS


def use_corpus(files):
    """Point citations at a throwaway corpus. The real corpus/ is never written."""
    root = tempfile.mkdtemp(prefix="kestrel-collision-corpus-")
    for name, text in files.items():
        with open(os.path.join(root, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    citations.CORPUS = root


def use_uploads(manifest=None):
    root = tempfile.mkdtemp(prefix="kestrel-collision-uploads-")
    path = os.path.join(root, "uploads.json")
    if manifest is not None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh)
    citations.UPLOADS = path
    return path


# --- 1. two corpus files, one fingerprint: neither owns it ----------------------------
use_corpus({"05_policy_A.md": TEXT_A, "06_policy_B.md": TEXT_B,
            "07_handbook.md": TEXT_UNIQUE})
m = citations._corpus_fingerprints()
check("two corpus files sharing a fingerprint name neither file",
      m.get(COLLIDED) is None, f"resolved to {m.get(COLLIDED)!r}")
check("a corpus file with a unique opening still names itself",
      m.get(citations._fingerprint(TEXT_UNIQUE)) == "07_handbook.md",
      f"got {m.get(citations._fingerprint(TEXT_UNIQUE))!r}")
check("the unambiguous map keeps every other file",
      len(m) == 1 and COLLIDED not in m, f"map is {m}")

# --- 2. an empty file must not adopt documents we could not fetch ---------------------
# One empty file only: two of them would collide, and the check would pass for the
# wrong reason (the collision guard, not the empty-content guard).
use_corpus({"07_empty.md": "", "09_real.md": TEXT_UNIQUE})
m = citations._corpus_fingerprints()
blank = citations._fingerprint("")
check("an empty corpus file contributes no fingerprint", blank not in m,
      f"'' -> {m.get(blank)!r}")
use_corpus({"07_empty.md": ""})
nmap = citations._name_map("acme-brain")
check("a failed raw fetch cannot borrow an empty file's name",
      citations._fingerprint(None or "") not in nmap,
      "fetch_raw returns None on error, which fingerprints to the same ''")

# --- 3. the collision table record_upload writes must actually be read ----------------
use_corpus({"09_real.md": TEXT_UNIQUE})
use_uploads()
citations.record_upload("acme-brain", [{"name": "hand_a.md", "text": TEXT_A},
                                       {"name": "hand_b.md", "text": TEXT_B}])
path = citations.UPLOADS
manifest = json.load(open(path, encoding="utf-8"))
clash = [k for k, v in manifest.get("_collisions", {}).items()
         if k.startswith("acme-brain::") and set(v) == {"hand_a.md", "hand_b.md"}]
check("record_upload still records the collision", bool(clash),
      f"_collisions is {manifest.get('_collisions')}")
check("and the first name is still the one the manifest kept",
      manifest["acme-brain"].get(COLLIDED) == "hand_a.md",
      f"manifest kept {manifest['acme-brain'].get(COLLIDED)!r}")
nmap = citations._name_map("acme-brain")
check("the recorded collision is honoured: the fingerprint names nothing",
      COLLIDED not in nmap,
      f"_name_map resolved the known-ambiguous fingerprint to {nmap.get(COLLIDED)!r}")
check("an unambiguous upload in the same dataset still resolves",
      citations._fingerprint(TEXT_UNIQUE) in nmap,
      "the sweep removed more than it should")

# --- 3b. the sweep must not punish documents that merely OPEN alike ------------------
# The collision table once keyed on the first 32 characters of the fingerprint, and the
# reader deleted every map key that STARTED WITH one. 32 normalised characters is about
# five words of boilerplate, so recording a clash between two `service level agreement
# credit…` documents also silenced a third document whose full 120-character
# fingerprint was unique. Ambiguity is a property of the whole fingerprint, so that is
# what the table stores and what the reader matches.
OPEN = "service level agreement credit policy "
BODY = ("applies to every account in the region and is administered by the finance "
        "team without exception per the published schedule and renewed each quarter.")
NEAR_A = OPEN + BODY + " Alpha document."
NEAR_B = OPEN + BODY + " Beta document."
NEAR_UNIQUE = OPEN + "differs here, well inside the fingerprint window, and is its own file."
assert len(citations._fingerprint(OPEN + BODY)) == 120, "A and B must share a fingerprint"
assert citations._fingerprint(NEAR_A)[:32] == citations._fingerprint(NEAR_UNIQUE)[:32], \
    "fixture must share its first 32 characters"
assert citations._fingerprint(NEAR_A) != citations._fingerprint(NEAR_UNIQUE), \
    "fixture must differ inside the 120-character fingerprint"

use_corpus({"x_1.md": NEAR_A, "x_2.md": NEAR_B, "z_unique.md": NEAR_UNIQUE})
use_uploads()
citations.record_upload("near-brain", [{"name": "x_1.md", "text": NEAR_A},
                                       {"name": "x_2.md", "text": NEAR_B}])
nmap = citations._name_map("near-brain")
check("a recorded clash is stored by its full fingerprint, not a truncation of it",
      any(key.endswith(citations._fingerprint(NEAR_A))
          for key in json.load(open(citations.UPLOADS, encoding="utf-8"))
          .get("_collisions", {})),
      "the collision key is shorter than the fingerprint it describes")
check("the clashing fingerprint names nothing",
      citations._fingerprint(NEAR_A) not in nmap)
check("but a document that merely opens the same way keeps its own citation",
      nmap.get(citations._fingerprint(NEAR_UNIQUE)) == "z_unique.md",
      f"got {nmap.get(citations._fingerprint(NEAR_UNIQUE))!r} — over-deleted")

# --- 3c. collisions of documents shorter than 120 chars must also be suppressed -------
SHORT_TEXT = "Short contract summary text under 120 chars."
assert len(citations._fingerprint(SHORT_TEXT)) < 120
use_corpus({"s_unique.md": "Different unique short text."})
use_uploads()
citations.record_upload("short-brain", [{"name": "short_1.md", "text": SHORT_TEXT},
                                        {"name": "short_2.md", "text": SHORT_TEXT}])
nmap = citations._name_map("short-brain")
check("a collision of documents shorter than 120 chars is also suppressed",
      citations._fingerprint(SHORT_TEXT) not in nmap,
      f"got {nmap.get(citations._fingerprint(SHORT_TEXT))!r} — short collision was not suppressed")

# --- 4. the tenant's own filename beats the demo file's, for identical content --------
use_corpus({"05_policy_SLA.md": TEXT_A})
use_uploads({"acme-brain": {COLLIDED: "our_sla_policy.md"}})
nmap = citations._name_map("acme-brain")
check("an upload that matches corpus content is labelled with the tenant's name",
      nmap.get(COLLIDED) == "our_sla_policy.md",
      f"got {nmap.get(COLLIDED)!r}")

# --- 5. another dataset's collisions do not blind this one ----------------------------
use_corpus({"05_policy_SLA.md": TEXT_A})
use_uploads({"acme-brain": {COLLIDED: "our_sla_policy.md"},
             "_collisions": {"other-brain::" + COLLIDED: ["x.md", "y.md"]}})
nmap = citations._name_map("acme-brain")
check("a collision recorded for a different brain leaves this one intact",
      nmap.get(COLLIDED) == "our_sla_policy.md",
      f"got {nmap.get(COLLIDED)!r}")


citations.CORPUS = REAL_CORPUS
demo = citations._corpus_fingerprints()
files = [n for n in sorted(os.listdir(REAL_CORPUS))
         if os.path.isfile(os.path.join(REAL_CORPUS, n))
         and citations._fingerprint(open(os.path.join(REAL_CORPUS, n),
                                         encoding="utf-8", errors="replace").read())]
check("the shipped demo corpus still names every one of its documents",
      len(demo) == len(files),
      f"{len(files)} documents, {len(demo)} unambiguous fingerprints — a corpus pair now "
      "shares its first 120 characters and one of the two has lost its citation")

citations.CORPUS, citations.UPLOADS = REAL_CORPUS, REAL_UPLOADS
print("CITATION COLLISIONS (ambiguous means unresolved, never guessed):",
      "FAIL" if FAILS else "PASS")
if FAILS:
    print(f"  {len(FAILS)} of {CHECKS} checks failed: {', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
