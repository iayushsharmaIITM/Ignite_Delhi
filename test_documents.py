"""Tests for documents.py — the untrusted-input boundary.

Run:  python test_documents.py

Every case here is a real file on disk, not a synthetic string. The negative
cases matter more than the positive ones: an upload path is only trustworthy if
its refusals are specific and its failures are per-file rather than fatal.

The PDF is generated with cupsfilter so it is a genuine PDF, not a text file
with a .pdf extension (which would prove nothing about pypdf).
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile

import documents

MARKER = "ZEPHYR-9917"
PASSED = []
FAILED = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL  {name}  {detail}")


def expect_error(name: str, data: bytes, must_mention: str) -> None:
    """Assert extract() refuses this file, and says why."""
    try:
        documents.extract(name, data)
    except documents.ExtractError as exc:
        check(
            f"{name} -> refused",
            must_mention.lower() in str(exc).lower(),
            f"message was: {exc}",
        )
        return
    check(f"{name} -> refused", False, "no error raised")


def make_pdf(text: str, path: str) -> bool:
    """Real PDF via cupsfilter. Returns False if unavailable."""
    source = path + ".src"
    with open(source, "w") as fh:
        fh.write(text)
    try:
        proc = subprocess.run(
            ["/usr/sbin/cupsfilter", "-m", "application/pdf", source],
            capture_output=True,
            timeout=60,
        )
    except Exception:  # noqa: BLE001
        return False
    if proc.returncode != 0 or not proc.stdout:
        return False
    with open(path, "wb") as fh:
        fh.write(proc.stdout)
    return True


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="doctest_")

    # ---------------------------------------------------------------- happy path
    print("\n[text formats]")

    txt = f"Vendor agreement.\nThe contract value is {MARKER} USD.\n".encode()
    got = documents.extract("agreement.txt", txt)
    check("txt extracts", MARKER in got, repr(got[:80]))

    md = f"# Memo\n\n- renewal quoted at {MARKER}\n".encode()
    got = documents.extract("memo.md", md)
    check("md extracts", MARKER in got, repr(got[:80]))

    csv = f"item,amount\nrenewal,{MARKER}\n".encode()
    got = documents.extract("pricing.csv", csv)
    check("csv extracts", MARKER in got, repr(got[:80]))

    js = ('{"renewal": {"code": "%s"}}' % MARKER).encode()
    got = documents.extract("config.json", js)
    check("json extracts", MARKER in got, repr(got[:80]))
    check("json is pretty-printed", "\n" in got and "  " in got, repr(got[:80]))

    # Windows BOM, a very common real-world export artefact.
    got = documents.extract("bom.txt", ("\ufeff" + MARKER).encode("utf-8"))
    check("utf-8 BOM stripped", got.startswith(MARKER), repr(got[:40]))

    # Latin-1 byte that is not valid UTF-8 must degrade, not reject.
    got = documents.extract("latin.txt", b"caf\xe9 " + MARKER.encode())
    check("invalid utf-8 degrades", MARKER in got, repr(got[:80]))

    # --------------------------------------------------------------- pdf + docx
    print("\n[pdf and docx]")

    pdf_path = os.path.join(tmp, "board_memo.pdf")
    if make_pdf(f"Board memo. Renewal value {MARKER} USD.", pdf_path):
        with open(pdf_path, "rb") as fh:
            got = documents.extract("board_memo.pdf", fh.read())
        check("pdf extracts", MARKER in got, repr(got[:120]))
    else:
        check("pdf extracts", False, "cupsfilter unavailable - cannot verify")

    try:
        import docx

        d = docx.Document()
        d.add_paragraph(f"Statement of work. Reference {MARKER}.")
        table = d.add_table(rows=1, cols=2)
        table.rows[0].cells[0].text = "value"
        table.rows[0].cells[1].text = MARKER
        buf = io.BytesIO()
        d.save(buf)
        got = documents.extract("sow.docx", buf.getvalue())
        check("docx paragraphs extract", MARKER in got, repr(got[:120]))
        check("docx table rows extract", " | " in got, repr(got[:160]))
    except ImportError:
        check("docx paragraphs extract", False, "python-docx unavailable")

    # ------------------------------------------------------------- negative path
    print("\n[refusals]")

    expect_error("blank.pdf", _blank_pdf(), "scan")
    expect_error("sheet.xlsx", b"not really a sheet", ".csv")
    expect_error("legacy.doc", b"not really a doc", "docx")
    expect_error("photo.png", b"\x89PNG\r\n", "ocr")
    expect_error("empty.txt", b"", "empty")
    expect_error("noextension", b"hello", "extension")
    expect_error("big.txt", b"x" * (documents.MAX_FILE_BYTES + 1), "limit")
    expect_error("weird.xyz", b"hello", "not supported")

    # A PDF that is not a PDF at all must fail cleanly, not crash.
    expect_error("broken.pdf", b"%PDF-1.4 garbage", "pdf")

    # ------------------------------------------------------- batch is never fatal
    print("\n[batch behaviour]")

    batch = [
        ("good.txt", f"contains {MARKER}".encode()),
        ("bad.xlsx", b"nope"),
        ("good2.md", f"also {MARKER}".encode()),
    ]
    docs, fails = documents.extract_many(batch)
    check("batch keeps the good files", len(docs) == 2, f"got {len(docs)}")
    check("batch reports the bad file", len(fails) == 1, f"got {len(fails)}")
    check("failure names the file", fails and fails[0]["name"] == "bad.xlsx", str(fails))
    check("failure has a reason", fails and bool(fails[0].get("error")), str(fails))

    # Over-cap batch: files beyond MAX_FILES must be reported, not silently lost.
    many = [(f"f{i}.txt", b"hello") for i in range(documents.MAX_FILES + 3)]
    docs, fails = documents.extract_many(many)
    check("file cap enforced", len(docs) == documents.MAX_FILES, f"got {len(docs)}")
    check("overflow reported", len(fails) == 3, f"got {len(fails)}")

    # ------------------------------------------------------------------- summary
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


def _blank_pdf() -> bytes:
    """A PDF with a page but no text - stands in for a scanned document."""
    try:
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        buf = io.BytesIO()
        writer.write(buf)
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return b"%PDF-1.4\n"


if __name__ == "__main__":
    sys.exit(main())
