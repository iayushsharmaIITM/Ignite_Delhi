"""Stage-2 OCR for chat attachments: read image-only PDFs with a vision model.

WHY A MODEL AND NOT TESSERACT: OCR engines are system binaries — brew on the
Mac, apt buildpacks on a host. A vision call reuses the OpenRouter key the
stack already carries, adds no system dependency, and behaves identically on
any future host.

THE LADDER (enforced by the caller in app.py):
  1. documents.extract — text-layer PDFs/DOCX, zero cost   (untouched)
  2. ocr.read_pdf      — PyMuPDF renders pages LOCALLY (free, offline),
                         ONE vision call reads them (max 10 pages / 3 MB)
  3. the honest 400     — blank pages get no invented text

Caps exist because OCR is the expensive path: it fires only when stage 1
found no text, and never runs away on a 400-page scan.
"""

from __future__ import annotations

import base64
import os

LIMIT_PAGES = 10
LIMIT_BYTES = 3 * 1024 * 1024          # rendered PNG budget
DPI = 110                              # enough for 10-12pt body text

PROMPT = (
    "Extract ALL text from these document pages, verbatim, in reading order. "
    "Preserve line breaks and section headings. Output only the extracted "
    "text - no commentary, no markdown fences, no summaries."
)


def _render(data: bytes) -> list[bytes]:
    """PDF bytes -> page PNGs. Local, offline, no key. Raises RuntimeError
    with a human message when the pages cannot be produced."""
    try:
        import pymupdf  # PyMuPDF
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "PDF image rendering is not installed (pip install PyMuPDF)."
        ) from exc
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("This PDF could not be opened.") from exc
    if doc.is_encrypted:
        raise RuntimeError("This PDF is password-protected.")
    if not len(doc):
        raise RuntimeError("This PDF has no pages.")
    pages: list[bytes] = []
    budget = LIMIT_BYTES
    for i in range(min(len(doc), LIMIT_PAGES)):
        png = doc[i].get_pixmap(dpi=DPI).tobytes("png")
        if len(png) > budget:
            break
        budget -= len(png)
        pages.append(png)
    if not pages:
        raise RuntimeError(
            f"This PDF's pages are too large to read (limit {LIMIT_PAGES} "
            f"pages / {LIMIT_BYTES // (1024 * 1024)} MB of images)."
        )
    return pages


def read_pdf(data: bytes) -> tuple[str, str]:
    """OCR a scanned PDF. Returns (text, model_used).

    Raises RuntimeError with a human message when OCR is unavailable or every
    configured model fails. Only ever called when stage 1 found no text.
    """
    import requests

    key = os.getenv("LLM_API_KEY", "")
    if not key:
        raise RuntimeError("OCR is not configured on this instance (no model key).")
    models = [
        m.strip() for m in os.getenv(
            "KESTREL_OCR_MODELS",
            "openai/gpt-6-luna,google/gemma-4-31b-it:free,qwen/qwen3.8-27b:free",
        ).split(",") if m.strip()
    ]
    endpoint = os.getenv(
        "KESTREL_OCR_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions"
    )

    pages = _render(data)
    content: list[dict] = [{"type": "text", "text": PROMPT}]
    for png in pages:
        content.append({
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()},
        })

    last = "no models configured"
    import time as _t
    t0 = _t.time()
    for model in models:
        try:
            r = requests.post(
                endpoint,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": content}],
                    "max_tokens": 4000,
                },
                headers={"Authorization": f"Bearer {key}"},
                timeout=120,
            )
            if r.status_code == 200:
                text = ((r.json().get("choices") or [{}])[0]
                        .get("message", {}).get("content") or "").strip()
                if text:
                    import observe  # P5 (fail-open)
                    observe.trace(
                        feature="ocr", model=model,
                        est_completion=len(text) // 4,
                        ms=int((_t.time() - t0) * 1000), ok=True,
                        meta={"pages": len(pages)},
                    )
                    return text, model
                last = f"{model}: empty response"
            else:
                last = f"{model}: HTTP {r.status_code} {r.text[:120]}"
        except Exception as exc:  # noqa: BLE001 - try the next model
            last = f"{model}: {exc}"
    raise RuntimeError(f"OCR could not read this PDF - {last}")


def available() -> bool:
    """Cheap gate: is stage 2 even possible in this process?"""
    if not os.getenv("LLM_API_KEY"):
        return False
    try:
        import pymupdf  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False
