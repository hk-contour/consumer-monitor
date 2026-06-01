"""PDF text extraction for legal / regulatory docs published as binary PDFs.

Same FetchResult contract as static_pages.fetch_and_extract so the
orchestrator and snapshot store don't care whether a URL is HTML or PDF.

Triggered by static_pages.fetch_and_extract when a URL ends in .pdf —
delegated here rather than skipped. Caller doesn't need to know.

Limits we accept:
- Image-only / scanned PDFs (no text layer) → returns fetch-failure
  with a specific error. Adding OCR (Tesseract) would unlock these
  but adds a system binary dependency; deferred.
- Encrypted PDFs → fail with parse error.
- Multi-column / table-heavy PDFs may produce reordered text — fine
  for diffing legal prose, less reliable for tables.
"""

from __future__ import annotations

import io
import sys

import requests

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # type: ignore

from .static_pages import (
    DEFAULT_TIMEOUT,
    FetchResult,
    MIN_EXTRACTED_CHARS,
    USER_AGENT,
    _strip_date_stamps,
)


def fetch_and_extract_pdf(url: str, timeout: int = DEFAULT_TIMEOUT) -> FetchResult:
    """Fetch a PDF URL and extract its text content.

    Returns the same FetchResult shape as static_pages.fetch_and_extract so
    callers can treat HTML and PDF results identically.
    """
    if pdfplumber is None:
        return FetchResult(
            ok=False,
            error="pdfplumber not installed — `pip install pdfplumber`",
        )

    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    except requests.RequestException as e:
        return FetchResult(ok=False, error=str(e))

    if r.status_code >= 400:
        return FetchResult(ok=False, status=r.status_code,
                           error=f"HTTP {r.status_code}")

    # Sanity-check the response is actually a PDF (some servers return HTML
    # error pages with .pdf URLs)
    if not r.content[:5] == b"%PDF-":
        return FetchResult(ok=False, status=r.status_code,
                           error="response not a PDF (no %PDF- magic bytes)")

    try:
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
    except Exception as e:
        return FetchResult(ok=False, status=r.status_code,
                           error=f"PDF parse error: {e}")

    raw_text = "\n".join(pages)
    if len(raw_text) < MIN_EXTRACTED_CHARS:
        return FetchResult(
            ok=False, status=r.status_code,
            error=f"PDF extracted only {len(raw_text)} chars "
                  "(likely scanned / image-only PDF; needs OCR)",
        )

    # Same post-processing pipeline as HTML: collapse whitespace, strip
    # publisher freshness-stamp dates so a routine re-issue doesn't fire.
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    cleaned = _strip_date_stamps("\n".join(lines))

    return FetchResult(ok=True, text=cleaned, status=r.status_code)
