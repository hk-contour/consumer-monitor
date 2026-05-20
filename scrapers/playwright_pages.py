"""Playwright (headless Chromium) for JS-rendered pages.

STUB. Build out per the briefing in build order step 8.

Required for: DASH merchant pricing, CART plans, MTCH subscription tiers,
PYPL merchant fees, KLAR (entire site), Z Premier Agent pricing, DUOL Plus.

Before writing a Playwright scraper for any URL: open DevTools Network ->
Fetch/XHR. If the page fetches data from a background JSON API, call that
endpoint with requests instead. Faster, lighter, more stable.
"""

from __future__ import annotations


def fetch_rendered(url: str, selector: str | None = None,
                   wait_ms: int = 2000) -> str:
    """Headless Chromium fetch. Returns extracted text or raises."""
    raise NotImplementedError(
        "Playwright scraper not yet built — see briefing build order step 8."
    )
