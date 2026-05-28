"""SEC EDGAR filings — use the JSON submissions API, not HTML scraping.

Endpoint:
    https://data.sec.gov/submissions/CIK{padded_to_10_digits}.json

Rate limit: 10 req/sec. We're well under that with 7 high-tier + 21 medium-tier
calls per run.

Ticker -> CIK lookup: https://www.sec.gov/files/company_tickers.json
Cached on disk after first fetch.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

MAX_AGE_DAYS = 3  # Only flag filings within this window

UA = "consumer-monitor/0.1 (Contour Asset Management; hari.kumar@contourasset.com)"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
CACHE_DIR = Path(__file__).resolve().parent.parent / "snapshots" / "_edgar_cache"

# Manual CIK overrides for tickers that may lag in SEC's company_tickers.json
# (recent IPOs, ticker changes, etc.). Checked before the fetched map.
TICKER_CIK_OVERRIDES: dict[str, str] = {
    "KLAR": "0002003292",  # Klarna Group plc; IPO'd Sept 2025
}


@dataclass
class Filing:
    accession: str
    form: str        # e.g. "10-Q", "8-K", "20-F"
    filed_date: str  # YYYY-MM-DD
    primary_doc: str
    url: str


def _headers() -> dict[str, str]:
    return {"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}


def _load_ticker_map() -> dict[str, str]:
    """Return {ticker_upper: zero-padded 10-digit CIK string}."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / "ticker_to_cik.json"
    if cache.exists() and (time.time() - cache.stat().st_mtime) < 86400 * 7:
        return json.loads(cache.read_text())

    r = requests.get(TICKERS_URL, headers=_headers(), timeout=30)
    r.raise_for_status()
    raw = r.json()
    # Format: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    out = {row["ticker"].upper(): str(row["cik_str"]).zfill(10)
           for row in raw.values()}
    cache.write_text(json.dumps(out))
    return out


def cik_for(ticker: str) -> str | None:
    t = ticker.strip().upper()
    if t in TICKER_CIK_OVERRIDES:
        return TICKER_CIK_OVERRIDES[t]
    return _load_ticker_map().get(t)


def recent_filings(ticker: str, limit: int = 25) -> list[Filing]:
    cik = cik_for(ticker)
    if not cik:
        return []
    r = requests.get(SUBMISSIONS_URL.format(cik=cik), headers=_headers(), timeout=30)
    r.raise_for_status()
    data = r.json()
    recent = data.get("filings", {}).get("recent", {})

    out: list[Filing] = []
    accessions = recent.get("accessionNumber", [])
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    primary_docs = recent.get("primaryDocument", [])

    for i, acc in enumerate(accessions[:limit]):
        acc_nodash = acc.replace("-", "")
        primary = primary_docs[i] if i < len(primary_docs) else ""
        url = (f"https://www.sec.gov/Archives/edgar/data/"
               f"{int(cik)}/{acc_nodash}/{primary}")
        out.append(Filing(
            accession=acc,
            form=forms[i] if i < len(forms) else "",
            filed_date=dates[i] if i < len(dates) else "",
            primary_doc=primary,
            url=url,
        ))
    return out


def is_recent(filed_date: str, max_age_days: int = MAX_AGE_DAYS) -> bool:
    """True if filed_date (YYYY-MM-DD) is within max_age_days of now."""
    if not filed_date:
        return False
    try:
        dt = datetime.strptime(filed_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return dt >= datetime.now(timezone.utc) - timedelta(days=max_age_days)


def new_filings_since(ticker: str, last_accession: str | None,
                      max_age_days: int = MAX_AGE_DAYS) -> list[Filing]:
    """Return filings (a) newer than last_accession AND (b) within max_age_days.

    Filings older than max_age_days are excluded even on first run. This means
    a quiet name with no recent activity produces an empty list — and the
    caller should still persist the top accession so subsequent runs can
    detect new arrivals cleanly.
    """
    filings = recent_filings(ticker)
    out: list[Filing] = []
    for f in filings:
        if last_accession and f.accession == last_accession:
            break
        if not is_recent(f.filed_date, max_age_days):
            continue
        out.append(f)
    return out
