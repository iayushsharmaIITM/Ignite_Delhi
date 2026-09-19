"""Vercel serverless entrypoint.

Vercel's Python runtime looks for an ASGI/WSGI callable. The application itself
lives in the repo root (app.py) because it is also run directly with
`python app.py` for local development and on Render, where it is a long-lived
process. This file exists only to expose it.

Deploy settings:
  - Vercel reads requirements.txt from the repo root automatically.
  - vercel.json rewrites every path here so the FastAPI routes own the URLs.

IMPORTANT LIMIT: Vercel serverless functions have a request timeout (10s on
Hobby, 60s on Pro) and no streaming beyond that window. /api/ask takes ~16-31s
against the live tenant, so on Hobby it will time out. See DEPLOY_VERCEL.md -
the graph, brains list and every page work; the ask path needs a Pro plan, a
longer maxDuration, or a different host.
"""

import os
import sys

# The app package lives one level up from api/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402,F401  - Vercel looks for this callable
