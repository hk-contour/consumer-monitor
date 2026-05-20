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
from pathlib import Path

import requests

UA = "consumer-monitor/0.1 (Contour Asset Management; hari.kumar@contourasset.com)"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
CACHE_DIR = Path(__file__).resolve().parent.parent / "snapshots" / "_edgar_cache"


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
    return _load_ticker_map().get(ticker.strip().upper())


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


def new_filings_since(ticker: str, last_accession: str | None) -> list[Filing]:
    """Return filings newer than last_accession (in API order: newest first)."""
    filings = recent_filings(ticker)
    if last_accession is None:
        return filings[:5]  # First run: take the most recent 5
    out: list[Filing] = []
    for f in filings:
        if f.accession == last_accession:
            break
        out.append(f)
    return out
