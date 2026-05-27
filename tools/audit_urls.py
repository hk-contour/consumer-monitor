"""URL audit: HEAD/GET every URL in the xlsx, classify, report failures.

Phase 0 tool. Run before iterating on scrapers — bad URLs in the config produce
either silent garbage or noisy failures.

Usage:
    python tools/audit_urls.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scrapers.config_reader import load_companies  # noqa: E402

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) consumer-monitor/0.1"
TIMEOUT = 20


def check(url: str) -> tuple[int, str, str]:
    """Return (status, final_url, error)."""
    try:
        # Some sites 405 HEAD — fall back to GET with stream so we don't pull body
        r = requests.head(url, headers={"User-Agent": UA}, allow_redirects=True,
                          timeout=TIMEOUT)
        if r.status_code in (405, 403, 501):
            r = requests.get(url, headers={"User-Agent": UA}, allow_redirects=True,
                             timeout=TIMEOUT, stream=True)
            r.close()
        return r.status_code, r.url, ""
    except requests.RequestException as e:
        return 0, url, type(e).__name__


def main() -> int:
    cos = load_companies()
    print(f"Auditing {len(cos)} companies × ~8 URL columns = ~{len(cos)*8} URLs\n")

    failures: list[tuple[str, str, str, int, str, str]] = []
    redirects: list[tuple[str, str, str, str]] = []
    ok = 0
    total = 0

    for c in cos:
        for source, url in c.urls.items():
            total += 1
            status, final_url, err = check(url)
            tag = "OK   " if 200 <= status < 300 else f"FAIL "
            print(f"  [{c.ticker:9s}] {source:20s} {status or err:>4} {url[:80]}")
            if 200 <= status < 300:
                ok += 1
                if final_url != url and not final_url.startswith(url.rstrip("/")):
                    redirects.append((c.ticker, source, url, final_url))
            else:
                failures.append((c.ticker, c.company, source, status, url, err))
            time.sleep(0.15)  # polite

    print()
    print("=" * 80)
    print(f"SUMMARY: {ok}/{total} URLs returned 2xx")
    print(f"Failures: {len(failures)}")
    print(f"Notable redirects: {len(redirects)}")
    print()

    if failures:
        print("--- FAILURES ---")
        for tkr, co, src, status, url, err in failures:
            print(f"\n{tkr} {co}")
            print(f"  source: {src}")
            print(f"  status: {status or err}")
            print(f"  url:    {url}")

    if redirects:
        print("\n--- REDIRECTS (potentially stale URLs) ---")
        for tkr, src, orig, final in redirects:
            print(f"\n  {tkr}/{src}")
            print(f"    orig:  {orig}")
            print(f"    final: {final}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
