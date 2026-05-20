"""Main orchestrator.

Usage:
    python run.py --tier high     # check high-priority names only
    python run.py --tier medium   # check medium-priority names
    python run.py --tier all      # high + medium (skips blocked)
    python run.py --ticker SHOP   # one-off run for a single ticker

Reads URL Registry from config/company_urls_jc.xlsx, runs the applicable
scrapers per source type, compares against stored snapshots, writes a markdown
digest to monitoring_system/, appends flagged rows to the Signal Feedback Log,
and (in GitHub Actions) commits updated snapshots so git history is the
changelog.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from dataclasses import dataclass

from digest import Change, write_digest
from feedback_log import append_changes
from scrapers import edgar, static_pages
from scrapers.config_reader import Company, load_companies
from scrapers.snapshot_store import compare, log_change, write_snapshot
from scrapers.tiers import blocker_reason

# Which URL fields should be scraped as static HTML (not behind JS, not an API)
STATIC_SOURCES = ("terms", "management_team", "pricing", "newsroom", "investor_relations")


def _short_summary(diff_text: str, source: str) -> str:
    """Pull a one-line summary from a unified diff — first changed line."""
    for line in diff_text.splitlines():
        if line.startswith(("+ ", "- ")) and not line.startswith(("+++", "---")):
            snippet = line[2:].strip()
            if snippet:
                return f"{source}: {snippet[:140]}"
    return f"{source}: change detected"


def check_static_url(c: Company, source: str, url: str) -> Change | None:
    res = static_pages.fetch_and_extract(url)
    if not res.ok:
        print(f"  [{c.ticker}/{source}] fetch failed: {res.error}", file=sys.stderr)
        return None
    diff_res = compare(c.ticker, source, res.text)
    if not diff_res.changed:
        return None
    write_snapshot(c.ticker, source, res.text)
    log_change(c.ticker, source, url, diff_res.diff_text)
    return Change(
        ticker=c.ticker,
        company=c.company,
        source=source,
        url=url,
        summary=_short_summary(diff_res.diff_text, source),
        diff=diff_res.diff_text,
    )


def check_edgar(c: Company) -> list[Change]:
    """Detect new SEC filings by accession number."""
    if not c.urls.get("regulatory_filings"):
        return []
    # Snapshot stores the most recent accession we've seen.
    state_key = "edgar_last_accession"
    from scrapers.snapshot_store import _path  # internal helper
    state_path = _path(c.ticker, state_key)
    last_acc = state_path.read_text().strip() if state_path.exists() else None
    try:
        new = edgar.new_filings_since(c.ticker, last_acc)
    except Exception as e:
        print(f"  [{c.ticker}/edgar] error: {e}", file=sys.stderr)
        return []
    if not new:
        return []
    # Update state to the newest accession
    write_snapshot(c.ticker, state_key, new[0].accession)
    changes: list[Change] = []
    for f in new:
        summary = f"New {f.form} filed {f.filed_date} (accession {f.accession})"
        changes.append(Change(
            ticker=c.ticker, company=c.company,
            source=f"edgar:{f.form}",
            url=f.url, summary=summary,
            diff=f"+ {summary}\n+ {f.url}",
        ))
        log_change(c.ticker, f"edgar:{f.form}", f.url, summary)
    return changes


def process_company(c: Company) -> list[Change]:
    print(f"[{c.ticker}] tier={c.tier} urls={len(c.urls)}")
    found: list[Change] = []
    for source in STATIC_SOURCES:
        url = c.urls.get(source)
        if not url:
            continue
        try:
            ch = check_static_url(c, source, url)
        except Exception:
            print(f"  [{c.ticker}/{source}] uncaught exception:", file=sys.stderr)
            traceback.print_exc()
            continue
        if ch:
            found.append(ch)
    found.extend(check_edgar(c))
    return found


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tier", choices=["high", "medium", "all"], default="high")
    p.add_argument("--ticker", help="Run for a single ticker, overrides --tier")
    args = p.parse_args()

    companies = load_companies()

    if args.ticker:
        target = [c for c in companies if c.ticker.upper() == args.ticker.upper()]
        if not target:
            print(f"Ticker {args.ticker} not found", file=sys.stderr)
            return 1
        tier_label = args.ticker.upper()
    else:
        wanted = {"high"} if args.tier == "high" else (
            {"medium"} if args.tier == "medium" else {"high", "medium"}
        )
        target = [c for c in companies if c.tier in wanted]
        tier_label = args.tier

    # Skip blocked names with a clear log entry
    for c in companies:
        if c.tier == "blocked":
            print(f"[{c.ticker}] BLOCKED: {blocker_reason(c.ticker)}", file=sys.stderr)

    all_changes: list[Change] = []
    for c in target:
        try:
            all_changes.extend(process_company(c))
        except Exception:
            print(f"[{c.ticker}] FATAL:", file=sys.stderr)
            traceback.print_exc()

    digest_path = write_digest(all_changes, tier_label)
    print(f"\nDigest written: {digest_path}")
    print(f"Flagged changes: {len(all_changes)}")

    if all_changes:
        try:
            append_changes(all_changes)
            print("Signal Feedback Log updated.")
        except Exception as e:
            print(f"Could not update feedback log: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
