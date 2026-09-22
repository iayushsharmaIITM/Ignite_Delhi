"""Prove tenant isolation — and prove it fails closed.

This is the test that decides whether the app is safe to put in front of two
customers. It checks the thing that actually matters: **tenant A must not be
able to read tenant B's brain**, and a caller with no key or a wrong key must
get nothing rather than everything.

Run it against a live server:

    python test_tenants.py                      # expects no tenants configured
    python test_tenants.py --with-tenants       # writes a tenant file first

The --with-tenants mode writes fixtures/tenants.json, runs the checks, and
removes it afterwards, so it is safe to run on a working tree.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import urllib.error
import urllib.request

BASE = os.environ.get("BASE", "http://127.0.0.1:8000")
HERE = pathlib.Path(__file__).parent
TENANTS = HERE / "fixtures" / "tenants.json"

# Two tenants with disjoint datasets. KEY_A must reach ONLY acme_industrial.
KEY_A, KEY_B = "test-key-aaaa-1111", "test-key-bbbb-2222"
TENANT_FILE = {
    "tenants": [
        {"id": "acme", "key": KEY_A, "datasets": ["acme_industrial"]},
        {"id": "kestrel", "key": KEY_B, "datasets": ["kestrel_full"]},
    ]
}

PASSED: list[str] = []
FAILED: list[str] = []


def get(path: str, key: str | None = None, timeout: int = 30):
    """Return (status, body). Never raises on an HTTP error status."""
    req = urllib.request.Request(BASE + path)
    if key:
        req.add_header("X-API-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, res.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    (PASSED if ok else FAILED).append(name)


def check_backward_compatible() -> None:
    """With no tenant file, nothing changes. The demo must not break."""
    print("\n[no tenants configured — behaviour must be unchanged]")
    for path in [
        "/api/stats?dataset=company_brain",
        "/api/stats?dataset=default_dataset",
        "/api/brains",
        "/health",
    ]:
        status, _ = get(path)
        check(f"{path} still reachable", status == 200, f"got {status}")


def check_isolation() -> None:
    """With tenants configured, isolation must hold and must fail closed."""
    print("\n[tenants configured — isolation must hold]")

    # --- the allow-list is enforced -----------------------------------------
    status, _ = get("/api/stats?dataset=acme_industrial", KEY_A)
    check("A may read its own brain", status == 200, f"got {status}")

    status, body = get("/api/stats?dataset=kestrel_full", KEY_A)
    check("A is REFUSED B's brain", status == 403, f"got {status}")

    status, body = get("/api/stats?dataset=acme_industrial", KEY_B)
    check("B is REFUSED A's brain", status == 403, f"got {status}")

    # --- the same must hold on every read route -----------------------------
    for path in [
        "/api/ask?q=test&dataset=kestrel_full",
        "/api/graph?dataset=kestrel_full",
        "/api/source?name=05_policy_SLA-credit-01.md&dataset=kestrel_full",
    ]:
        status, _ = get(path, KEY_A)
        check(f"A refused on {path.split('?')[0]}", status == 403, f"got {status}")

    # --- delete is the dangerous one ----------------------------------------
    req = urllib.request.Request(BASE + "/api/brains/kestrel_full", method="DELETE")
    req.add_header("X-API-Key", KEY_A)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            status = res.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except Exception:
        status = 0
    check("A cannot DELETE B's brain", status == 403, f"got {status}")

    # --- fail closed ---------------------------------------------------------
    status, _ = get("/api/stats?dataset=acme_industrial")
    check("no key is refused (401, not 200)", status == 401, f"got {status}")

    status, _ = get("/api/stats?dataset=acme_industrial", "wrong-key")
    check("a wrong key is refused", status == 401, f"got {status}")

    # --- shared reference material stays reachable ---------------------------
    status, _ = get("/api/stats?dataset=company_brain", KEY_A)
    check("shared demo brain still reachable", status == 200, f"got {status}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-tenants", action="store_true",
                    help="write fixtures/tenants.json, test isolation, then remove it")
    args = ap.parse_args()

    print("Tenant isolation test")

    if not args.with_tenants:
        check_backward_compatible()
    else:
        TENANTS.parent.mkdir(parents=True, exist_ok=True)
        backup = TENANTS.read_text(encoding="utf-8") if TENANTS.exists() else None
        TENANTS.write_text(json.dumps(TENANT_FILE, indent=1), encoding="utf-8")
        try:
            # The config is read per request, so no restart is needed.
            check_isolation()
        finally:
            if backup is None:
                TENANTS.unlink(missing_ok=True)
            else:
                TENANTS.write_text(backup, encoding="utf-8")
            print("\n  (tenants.json restored)")

    print()
    if FAILED:
        print(f"{len(FAILED)} FAILED: " + ", ".join(FAILED))
        return 1
    print(f"All {len(PASSED)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
