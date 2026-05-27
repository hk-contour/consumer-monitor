"""Static-HTML scraper: requests + BeautifulSoup + hash/diff.

For T&C, management team, static pricing, newsroom pages without RSS, etc.
Pattern: fetch -> extract text from target selector -> compare via snapshot_store.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "consumer-monitor/0.1 (Contour Asset Management research; "
    "contact: hari.kumar@contourasset.com)"
)

DEFAULT_TIMEOUT = 30
STRIP_TAGS = ("script", "style", "noscript", "nav", "header", "footer")

# Heading text patterns that introduce noisy sections we want to strip — e.g.
# geo-personalized store widgets, recommendation carousels, "trending now"
# blocks. Matched case-insensitive as substrings of <h1>/<h2>/<h3> text.
# When found, the heading element and all subsequent siblings *and* their
# following document-order elements are dropped until the next heading at the
# same level or higher.
NOISE_HEADING_PATTERNS = (
    "shop local stores near you",
    "trending now",
    "recently viewed",
    "you might also like",
    "you may also like",
    "more from",
    "featured stores",
    "explore more",
    "recommended for you",
)


@dataclass
class FetchResult:
    ok: bool
    text: str = ""
    status: int = 0
    error: str = ""


def fetch(url: str, timeout: int = DEFAULT_TIMEOUT) -> FetchResult:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    except requests.RequestException as e:
        return FetchResult(ok=False, error=str(e))
    if r.status_code >= 400:
        return FetchResult(ok=False, status=r.status_code,
                           error=f"HTTP {r.status_code}")
    return FetchResult(ok=True, text=r.text, status=r.status_code)


def _strip_noise_sections(root) -> None:
    """Remove subtrees introduced by noise headings (mutates `root` in place).

    For each h1/h2/h3 whose text matches NOISE_HEADING_PATTERNS, find the
    smallest ancestor that contains the heading but NOT the next heading at
    the same or higher level, then remove that ancestor. This correctly
    handles sites where the heading and its content sit in separate sibling
    divs at some level above the heading (e.g. Instacart Plus).
    """
    headings = list(root.find_all(["h1", "h2", "h3"]))
    if not headings:
        return
    for i, h in enumerate(headings):
        text = h.get_text(strip=True).lower()
        if not any(p in text for p in NOISE_HEADING_PATTERNS):
            continue
        level = int(h.name[1])
        # Locate the next "stopper" heading (same or higher level) in doc order
        next_h = None
        for j in range(i + 1, len(headings)):
            if int(headings[j].name[1]) <= level:
                next_h = headings[j]
                break
        # Walk up from h until we find an ancestor whose parent ALSO contains
        # the next heading — that's the boundary, and our ancestor is the
        # tightest scope encompassing only the noise section.
        ancestor = h
        while ancestor.parent is not None and ancestor.parent is not root:
            parent = ancestor.parent
            if next_h is None or next_h not in parent.descendants:
                ancestor = parent
                continue
            # parent contains next_h → don't include parent in the removal
            break
        if ancestor is not None and ancestor is not root:
            ancestor.decompose()


def extract_text(html: str, selector: str | None = None) -> str:
    """Strip junk tags and extract clean text. If selector given, narrow to it.

    selector can be a CSS selector ('main', 'div#content', etc). Without it,
    we use <body> minus the strip-list.

    After narrowing/stripping, also removes noise-introducing sections such
    as geo-personalized store widgets and recommendation carousels — see
    NOISE_HEADING_PATTERNS.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in STRIP_TAGS:
        for el in soup.find_all(tag):
            el.decompose()

    root = soup.select_one(selector) if selector else soup.body
    if root is None:
        root = soup

    _strip_noise_sections(root)

    text = root.get_text(separator="\n", strip=True)
    # Collapse runs of blank lines
    lines = [ln for ln in (s.strip() for s in text.splitlines()) if ln]
    return "\n".join(lines)


MIN_EXTRACTED_CHARS = 200  # Below this we treat the fetch as suspect (bot-stub etc.)


def fetch_and_extract(url: str, selector: str | None = None,
                      retries: int = 2, backoff: float = 1.5) -> FetchResult:
    last: FetchResult = FetchResult(ok=False, error="not attempted")
    for attempt in range(retries + 1):
        res = fetch(url)
        if res.ok:
            extracted = extract_text(res.text, selector)
            if len(extracted) < MIN_EXTRACTED_CHARS:
                # Likely a bot-stub / empty shell / blocked. Don't overwrite
                # the existing snapshot with this — treat as fetch failure.
                last = FetchResult(
                    ok=False, status=res.status,
                    error=f"suspect-empty (extracted={len(extracted)} chars, "
                          "below MIN_EXTRACTED_CHARS — likely bot detection)")
                continue
            return FetchResult(ok=True, text=extracted, status=res.status)
        last = res
        time.sleep(backoff ** attempt)
    return last
