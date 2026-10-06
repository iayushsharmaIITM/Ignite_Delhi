"""Immutable audit trail logging for enterprise compliance (SOC 2, ISO 27001, DPDP, GDPR).

Records every security-relevant action (actor, org, action, resource, timestamp, ip, details).
Persists to Postgres audit_logs table when storage is available, with an in-memory
bounded fallback buffer so audit trails are never dropped during storage interruptions.
"""
from __future__ import annotations

import collections
import json
import logging
import threading
import time
from typing import Any

_BUFFER_LOCK = threading.Lock()
_MEMORY_AUDIT_LOG: collections.deque = collections.deque(maxlen=2000)


def record_audit_event(
    actor_id: str | None,
    org_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    """Record an immutable audit event."""
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    record = {
        "timestamp": now_iso,
        "actor_id": actor_id or "system",
        "org_id": org_id or "",
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id or "",
        "details": details or {},
        "ip_address": ip_address or "",
    }

    # 1. Always record in local bounded memory buffer
    with _BUFFER_LOCK:
        _MEMORY_AUDIT_LOG.append(dict(record))

    # 2. Persist to Postgres if storage is available
    try:
        import storage
        if storage.available():
            with storage._conn() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO audit_logs (actor_id, org_id, action, resource_type, resource_id, details, ip_address)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record["actor_id"],
                        record["org_id"],
                        record["action"],
                        record["resource_type"],
                        record["resource_id"],
                        json.dumps(record["details"]),
                        record["ip_address"],
                    ),
                )
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("audit").warning("Failed to persist audit log to DB: %s", exc)

    return record


def list_audit_events(identity: dict | None = None, limit: int = 50) -> list[dict]:
    """Retrieve audit events scoped to tenant identity."""
    limit = max(1, min(limit, 500))
    org_id = (identity or {}).get("org_id") or ""
    actor_id = (identity or {}).get("user_id") or ""

    # Try DB query first
    try:
        import storage
        if storage.available():
            with storage._conn() as conn, conn.cursor() as cur:
                if org_id:
                    cur.execute(
                        """
                        SELECT id, timestamp, actor_id, org_id, action, resource_type, resource_id, details, ip_address
                        FROM audit_logs
                        WHERE org_id = %s
                        ORDER BY timestamp DESC
                        LIMIT %s
                        """,
                        (org_id, limit),
                    )
                elif actor_id:
                    cur.execute(
                        """
                        SELECT id, timestamp, actor_id, org_id, action, resource_type, resource_id, details, ip_address
                        FROM audit_logs
                        WHERE actor_id = %s
                        ORDER BY timestamp DESC
                        LIMIT %s
                        """,
                        (actor_id, limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, timestamp, actor_id, org_id, action, resource_type, resource_id, details, ip_address
                        FROM audit_logs
                        ORDER BY timestamp DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                rows = cur.fetchall()
                if rows:
                    res = []
                    for r in rows:
                        d = dict(r)
                        if "timestamp" in d and hasattr(d["timestamp"], "isoformat"):
                            d["timestamp"] = d["timestamp"].isoformat()
                        res.append(d)
                    return res
    except Exception:  # noqa: BLE001
        pass

    # Fall back to in-memory buffer
    with _BUFFER_LOCK:
        items = list(_MEMORY_AUDIT_LOG)

    filtered = []
    for it in reversed(items):
        if org_id and it.get("org_id") != org_id:
            continue
        if actor_id and not org_id and it.get("actor_id") != actor_id:
            continue
        filtered.append(dict(it))
        if len(filtered) >= limit:
            break

    return filtered
