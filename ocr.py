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
    if os.getenv("PROVIDER") == "mock":
        return ("[Mock Vision OCR] Scanned PDF text extracted.", "mock-vision")

    import requests

    import llm

    key = llm.api_key()
    if not key:
        raise RuntimeError("OCR is not configured on this instance (no model key).")
    default_vision = "google/gemini-2.0-flash-001,meta-llama/llama-3.2-11b-vision-instruct,qwen/qwen-2.5-vl-72b-instruct"
    models = [
        m.strip() for m in os.getenv(
            "KESTREL_OCR_MODELS", default_vision
        ).split(",") if m.strip()
    ]
    endpoint = os.getenv(
        "KESTREL_OCR_ENDPOINT", llm.chat_url() or "https://openrouter.ai/api/v1/chat/completions"
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
                timeout=90,
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


IMAGE_PROMPT = (
    "Extract and transcribe all text, numbers, code, and UI elements visible in this image or screenshot "
    "verbatim in reading order. Also provide a clear, concise summary of what the image shows "
    "(e.g., application interface, error banner, system diagram, data table, or document) so an assistant "
    "can answer user questions about it."
)


def read_image(data: bytes, mime_type: str = "image/png") -> tuple[str, str]:
    """OCR and transcribe an image (PNG, JPEG, WebP, etc.). Returns (text, model_used).

    Raises RuntimeError with a human message when OCR is unavailable or every
    configured model fails.
    """
    if os.getenv("PROVIDER") == "mock":
        return ("[Mock Vision OCR] Screenshot content extracted successfully.", "mock-vision")

    import requests

    import llm

    key = llm.api_key()
    if not key:
        raise RuntimeError("Vision OCR is not configured on this instance (no model key).")

    default_vision = "google/gemini-2.0-flash-001,meta-llama/llama-3.2-11b-vision-instruct,qwen/qwen-2.5-vl-72b-instruct"
    models = [
        m.strip() for m in os.getenv(
            "KESTREL_OCR_MODELS", default_vision
        ).split(",") if m.strip()
    ]
    endpoint = os.getenv(
        "KESTREL_OCR_ENDPOINT", llm.chat_url() or "https://openrouter.ai/api/v1/chat/completions"
    )

    if not mime_type or not mime_type.startswith("image/"):
        mime_type = "image/png"

    b64_img = base64.b64encode(data).decode("ascii")
    content: list[dict] = [
        {"type": "text", "text": IMAGE_PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_img}"}},
    ]

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
                timeout=90,
            )
            if r.status_code == 200:
                text = ((r.json().get("choices") or [{}])[0]
                        .get("message", {}).get("content") or "").strip()
                if text:
                    import observe
                    observe.trace(
                        feature="ocr-image", model=model,
                        est_completion=len(text) // 4,
                        ms=int((_t.time() - t0) * 1000), ok=True,
                        meta={"bytes": len(data), "mime": mime_type},
                    )
                    return text, model
                last = f"{model}: empty response"
            else:
                last = f"{model}: HTTP {r.status_code} {r.text[:120]}"
        except Exception as exc:  # noqa: BLE001
            last = f"{model}: {exc}"
    raise RuntimeError(f"OCR could not read this image - {last}")


def available() -> bool:
    """Cheap gate: is stage 2 vision / OCR possible in this process?"""
    if os.getenv("PROVIDER") == "mock":
        return True
    import llm
    return bool(llm.api_key())

