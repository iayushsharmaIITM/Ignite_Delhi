"""Langfuse bridge (P5): fire-and-forget observability for every LLM call.

DESIGN RULES (demo-critical, in priority order):
  * Fail-open, ALWAYS. No keys configured -> silent no-op. Network errors are
    dropped. Nothing in here can raise into a request path — the demo must
    never depend on Langfuse being up.
  * Zero dependencies: one HTTP POST per trace to the Langfuse ingestion API
    (Basic auth), posted from a daemon thread so request latency is untouched.
  * Bounded queue (500): under outage the oldest traces are dropped —
    observability must never consume unbounded memory.

USAGE
    observe.trace(feature="ask", brain="hghi", route="brain", model="...",
                  user="user_...", est_prompt=1234, est_completion=567,
                  ms=23000, ok=True)

Env: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
     (default https://cloud.langfuse.com). All optional — absent = disabled.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import threading
import time
import urllib.request
from datetime import datetime, timezone

_Q: "queue.Queue[dict]" = queue.Queue(maxsize=500)
_started = False
_lock = threading.Lock()


def _enabled() -> bool:
    return bool(
        os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
    )


def _auth_header() -> str:
    raw = (
        os.getenv("LANGFUSE_PUBLIC_KEY", "")
        + ":"
        + os.getenv("LANGFUSE_SECRET_KEY", "")
    ).encode()
    return "Basic " + base64.b64encode(raw).decode()


def _iso(ts: float | None = None) -> str:
    dt = datetime.fromtimestamp(ts or time.time(), tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _post(item: dict) -> None:
    host = (os.getenv("LANGFUSE_HOST") or "https://cloud.langfuse.com").rstrip("/")
    req = urllib.request.Request(
        host + "/api/public/ingestion",
        data=json.dumps({"batch": [item]}).encode(),
        headers={
            "Authorization": _auth_header(),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=10).read()


def _worker() -> None:
    while True:
        item = _Q.get()
        try:
            _post(item)
        except Exception:  # noqa: BLE001 - observability never raises
            pass
        finally:
            _Q.task_done()


def _ensure_worker() -> None:
    global _started
    with _lock:
        if not _started:
            threading.Thread(target=_worker, daemon=True, name="langfuse").start()
            _started = True


def trace(
    feature: str,
    *,
    brain: str | None = None,
    route: str | None = None,
    model: str | None = None,
    user: str | None = None,
    est_prompt: int = 0,
    est_completion: int = 0,
    ms: int | None = None,
    ok: bool = True,
    error: str | None = None,
    started_at: float | None = None,
    meta: dict | None = None,
) -> None:
    """Queue one LLM-call trace. Never raises; no-op when unconfigured."""
    if not _enabled():
        return
    _ensure_worker()
    try:
        now = time.time()
        start = started_at if started_at is not None else now - (ms or 0) / 1000.0
        metadata = {"brain": brain, "route": route, "feature": feature,
                    "ok": ok, **(meta or {})}
        if error:
            metadata["error"] = error[:300]
        body = {
            "name": feature,
            **({"userId": str(user)[:64]} if user else {}),
            "metadata": {k: v for k, v in metadata.items() if v is not None},
        }
        obs = {
            "id": f"obs_{int(now * 1000)}_{feature}",
            "type": "observation-create",
            "timestamp": _iso(now),
            "body": {
                "traceId": f"tr_{int(now * 1000)}_{feature}",
                "type": "GENERATION",
                "name": feature,
                "startTime": _iso(start),
                "endTime": _iso(now),
                **({"latencyMs": int(ms)} if ms is not None else {}),
                **({"model": model} if model else {}),
                "usage": {
                    "input": int(est_prompt or 0),
                    "output": int(est_completion or 0),
                    "unit": "TOKENS",
                },
                **({"level": "ERROR", "statusMessage": error[:200]}
                   if not ok and error else {}),
                "metadata": {k: v for k, v in metadata.items() if v is not None},
            },
        }
        item = {
            "id": f"tr_{int(now * 1000)}_{feature}",
            "type": "trace-create",
            "timestamp": _iso(now),
            "body": body,
        }
        _Q.put_nowait(item)
        _Q.put_nowait(obs)
    except Exception:  # noqa: BLE001 - never raise from observability
        pass


def pending() -> int:
    """Test/ops hook: how many traces are queued for delivery."""
    return _Q.qsize()
