"""Web tier: serves the UI and streams answers.

WHY THIS FILE EXISTS SEPARATELY FROM pipeline.py
Render task runs cannot accept inbound connections (no ports), so the workflow
can never serve the UI. Two services are mandatory:
  this web tier  ->  triggers runs  ->  Render Workflow (compute)
"""

import json
import os

# --- environment must load BEFORE memory_layer is imported ---------------
# memory_layer reads PROVIDER at import time, so a .env loaded afterwards
# would silently be ignored and the app would fall back to the mock provider.
HERE = os.path.dirname(os.path.abspath(__file__))

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(HERE, ".env"))
except ImportError:  # dotenv is optional; env vars still work
    pass

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402

import memory_layer  # noqa: E402
from memory_layer import recall  # noqa: E402

app = FastAPI(title="Kestrel Company Brain")


@app.get("/health")
def health():
    """Always have this. A health endpoint means the demo never looks dead."""
    payload = {
        "ok": True,
        "provider": memory_layer.PROVIDER,
        "dataset": os.getenv("COGNEE_DATASET", "company_brain"),
        "service": os.getenv("COGNEE_SERVICE_URL", ""),
    }
    # Prove the tenant instance is actually reachable, not just configured.
    if payload["provider"] == "cloud":
        try:
            import cognee_cloud

            upstream = cognee_cloud.health()
            payload["upstream"] = upstream.get("status", "unknown")
            payload["components"] = {
                k: v.get("status") for k, v in (upstream.get("components") or {}).items()
            }

            # The tenant's /health endpoint is UNAUTHENTICATED. It therefore
            # reports "healthy" even when our API key is wrong — we verified
            # this by pointing the app at a bad key and watching /health claim
            # everything was fine while every query returned 401. So probe an
            # authenticated endpoint too, or this check is worse than useless.
            try:
                cognee_cloud.datasets()
                payload["auth"] = "ok"
            except Exception as exc:  # noqa: BLE001
                payload["auth"] = "failed"
                payload["auth_error"] = str(exc)[:160]
        except Exception as exc:  # noqa: BLE001 - health must never raise
            payload["upstream"] = "unreachable"
            payload["upstream_error"] = str(exc)[:200]
    return payload


@app.get("/api/ask")
async def ask(q: str):
    """Stream the answer as newline-delimited JSON so the UI never sits blank."""

    async def gen():
        yield json.dumps({"stage": "start"}) + "\n"
        try:
            async for event in recall(q):
                yield json.dumps(event) + "\n"
        except Exception as exc:  # noqa: BLE001 - demo must never white-screen
            yield json.dumps({"stage": "error", "message": str(exc)}) + "\n"
        yield json.dumps({"stage": "done"}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.get("/api/graph")
def graph():
    """The knowledge graph, for the graph view."""
    try:
        import cognee_cloud

        return cognee_cloud.graph()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:300]}


@app.get("/api/stats")
def stats():
    """Graph size — cheap numbers that make the graph feel real.

    Uses /graph rather than /graph-summary: the summary endpoint returns
    numNodes 0 until a summary run has been computed, which would render as
    a confidently empty graph.
    """
    try:
        import cognee_cloud

        g = cognee_cloud.graph()
        return {
            "ok": True,
            "nodes": len(g.get("nodes", [])),
            "edges": len(g.get("edges", [])),
            "dataset": os.getenv("COGNEE_DATASET", "company_brain"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:300]}


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"))


@app.get("/graph")
def graph_page():
    return FileResponse(os.path.join(HERE, "static", "graph.html"))


if __name__ == "__main__":
    import uvicorn

    # Render injects PORT and requires binding to 0.0.0.0. Locally we want
    # 127.0.0.1. Same file works in both places with these two defaults.
    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
    )
