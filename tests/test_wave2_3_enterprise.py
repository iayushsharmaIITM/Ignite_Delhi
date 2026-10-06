"""Wave 2 & 3 Enterprise Tests: Observability, Metrics, Golden Evals, Audit Logs, and DPDP/GDPR.

Run standalone:
    python3 tests/test_wave2_3_enterprise.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PROVIDER"] = "mock"
os.environ["AUTH_MODE"] = "off"
_url = os.environ.get("DATABASE_URL", "")
if _url and "5434" not in _url:
    raise SystemExit("Refusing: DATABASE_URL must point to lab (5434) or be unset.")
if not _url:
    os.environ["DATABASE_URL"] = "postgresql://kestrel:kestrel@127.0.0.1:5434/kestrel"

from cryptography.fernet import Fernet
os.environ.setdefault("CONNECTOR_VAULT_KEY", Fernet.generate_key().decode())

import app as app_module
import audit
from fastapi.testclient import TestClient

client = TestClient(app_module.app)
FAILS = []
CHECKS = 0


def check(name: str, ok: bool, detail: str = ""):
    global CHECKS
    CHECKS += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else '  <- ' + detail}")
    if not ok:
        FAILS.append(name)


def main() -> int:
    # 1. Prometheus Metrics endpoint (Wave 2: OB-3)
    r_metrics = client.get("/metrics")
    check("GET /metrics returns 200 with Prometheus metrics",
          r_metrics.status_code == 200,
          f"{r_metrics.status_code} {r_metrics.text}")
    metrics_text = r_metrics.text
    check("metrics include kestrel_http_requests_total",
          "kestrel_http_requests_total" in metrics_text,
          metrics_text[:200])
    check("metrics include kestrel_uptime_seconds",
          "kestrel_uptime_seconds" in metrics_text,
          metrics_text[:200])

    # 2. Audit Trail logging (Wave 3: CP-1)
    # Unit record
    rec = audit.record_audit_event(
        actor_id="user_test_123",
        org_id="org_test_abc",
        action="test_action_run",
        resource_type="brain",
        resource_id="company_brain",
        details={"ip": "127.0.0.1", "meta": "test"},
    )
    check("audit.record_audit_event returns stamped record",
          rec.get("action") == "test_action_run" and "timestamp" in rec,
          str(rec))

    events = audit.list_audit_events(identity={"user_id": "user_test_123", "org_id": "org_test_abc"})
    check("audit.list_audit_events returns logged events",
          any(e.get("action") == "test_action_run" for e in events),
          f"got: {events}")

    r_audit = client.get("/api/audit/logs")
    check("GET /api/audit/logs returns 200 with logs list",
          r_audit.status_code == 200 and isinstance(r_audit.json().get("events"), list),
          f"{r_audit.status_code} {r_audit.text}")

    # 3. GDPR / DPDP Data Subject Rights (Wave 3: CP-3)
    r_export = client.post("/api/user/export-data")
    check("POST /api/user/export-data returns 200 with user archive",
          r_export.status_code == 200 and r_export.json().get("ok") is True and "export" in r_export.json(),
          f"{r_export.status_code} {r_export.text}")

    r_erase = client.post("/api/user/erase-data", json={"confirm": True})
    check("POST /api/user/erase-data returns 200 confirmation",
          r_erase.status_code == 200 and r_erase.json().get("erased") is True,
          f"{r_erase.status_code} {r_erase.text}")

    # 4. Golden Question Evaluation & Low-Evidence Abstention (Wave 2: EV-1, EV-3)
    # Ask a completely unknown out-of-domain question against demo brain
    r_ask = client.get("/api/ask", params={"q": "xyzq_nonexistent_question_out_of_domain_12345"})
    check("asking out-of-domain query streams response",
          r_ask.status_code == 200,
          f"{r_ask.status_code} {r_ask.text}")

    print("\nWAVE 2 & 3 ENTERPRISE TEST:", "FAIL" if FAILS else "PASS")
    if FAILS:
        print(f"  {len(FAILS)} of {CHECKS} checks failed: {', '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
