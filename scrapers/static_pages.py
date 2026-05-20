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


def extract_text(html: str, selector: str | None = None) -> str:
    """Strip junk tags and extract clean text. If selector given, narrow to it.

    selector can be a CSS selector ('main', 'div#content', etc). Without it,
    we use <body> minus the strip-list.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in STRIP_TAGS:
        for el in soup.find_all(tag):
            el.decompose()

    root = soup.select_one(selector) if selector else soup.body
    if root is None:
        root = soup

    text = root.get_text(separator="\n", strip=True)
    # Collapse runs of blank lines
    lines = [ln for ln in (s.strip() for s in text.splitlines()) if ln]
    return "\n".join(lines)


def fetch_and_extract(url: str, selector: str | None = None,
                      retries: int = 2, backoff: float = 1.5) -> FetchResult:
    last: FetchResult = FetchResult(ok=False, error="not attempted")
    for attempt in range(retries + 1):
        res = fetch(url)
        if res.ok:
            return FetchResult(ok=True, text=extract_text(res.text, selector),
                               status=res.status)
        last = res
        time.sleep(backoff ** attempt)
    return last
