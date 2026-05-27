"""Phase 1B: RSS discovery sweep.

For each newsroom URL of selected tickers, try two methods:
  1. HTML auto-discovery — fetch the page and look for <link rel="alternate"
     type="application/rss+xml"> (the publisher's declared feed URL).
  2. Path probing — try /feed, /rss, /rss.xml, /feed.xml, /atom.xml.

Method 1 is more reliable; method 2 is fallback. Reports which URLs have
RSS available so Phase 1C can swap them in.

Usage:
    python tools/discover_rss.py                  # default: SHOP,WIX,DASH,CART
    python tools/discover_rss.py SHOP,WIX,DASH,CART,ETSY
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scrapers.config_reader import load_companies  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) consumer-monitor/0.1"}
TIMEOUT = 15
PROBE_PATHS = ["/feed", "/rss", "/rss.xml", "/feed.xml", "/atom.xml",
               "/feed/", "/news/feed", "/press/feed"]


def autodiscover(url: str) -> list[str]:
    """Method 1: parse <link rel='alternate' type='...rss/atom...'>."""
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code >= 400:
            return []
    except requests.RequestException:
        return []
    soup = BeautifulSoup(r.text, "lxml")
    feeds = []
    for link in soup.find_all("link", rel="alternate"):
        t = (link.get("type") or "").lower()
        if "rss" in t or "atom" in t:
            href = link.get("href")
            if href:
                feeds.append(urljoin(r.url, href))
    return feeds


def probe_paths(base_url: str) -> list[str]:
    """Method 2: try common feed paths and check for XML-ish content."""
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    candidates = [origin + p for p in PROBE_PATHS]
    # Also try at the actual URL path
    candidates += [base_url.rstrip("/") + p for p in ("/feed", "/rss")]
    hits = []
    for c in candidates:
        try:
            r = requests.head(c, headers=UA, timeout=TIMEOUT, allow_redirects=True)
            if r.status_code >= 400:
                continue
            ctype = (r.headers.get("Content-Type") or "").lower()
            if "xml" in ctype or "rss" in ctype or "atom" in ctype:
                hits.append(r.url)
        except requests.RequestException:
            continue
    return list(dict.fromkeys(hits))  # dedup, preserve order


def main() -> int:
    default = "SHOP,WIX,DASH,CART"
    arg = sys.argv[1] if len(sys.argv) > 1 else default
    wanted = {t.strip().upper() for t in arg.split(",")}

    cos = [c for c in load_companies() if c.ticker.upper() in wanted]
    print(f"RSS discovery for {len(cos)} companies\n")

    findings: list[tuple[str, str, list[str]]] = []
    for c in cos:
        url = c.urls.get("newsroom")
        if not url:
            print(f"[{c.ticker}] no newsroom URL — skip")
            continue
        print(f"[{c.ticker}] {url}")
        feeds = autodiscover(url)
        if feeds:
            print(f"  auto-discovered:  {feeds[0]}")
            for extra in feeds[1:]:
                print(f"                    {extra}")
        else:
            print("  auto-discovered:  none")
            probed = probe_paths(url)
            if probed:
                print(f"  path probe found: {probed[0]}")
                feeds = probed
            else:
                print("  path probe found: none")
        findings.append((c.ticker, url, feeds))
        print()

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    have_rss = [f for f in findings if f[2]]
    no_rss = [f for f in findings if not f[2]]
    print(f"RSS available: {len(have_rss)}/{len(findings)}")
    for tkr, _, feeds in have_rss:
        print(f"  {tkr:6s} -> {feeds[0]}")
    if no_rss:
        print("No RSS detected:")
        for tkr, url, _ in no_rss:
            print(f"  {tkr:6s} ({url}) — Phase 1C falls back to HTML scrape")
    return 0


if __name__ == "__main__":
    sys.exit(main())
