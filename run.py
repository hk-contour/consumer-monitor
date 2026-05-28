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
import time
import traceback
from dataclasses import dataclass

from digest import Change, write_digest

# Single timestamp per process run — every Change emitted in this run shares it.
RUN_TS = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
from feedback_log import append_changes
from scrapers import edgar, edgar_enrich, rss, static_pages
from scrapers.config_reader import Company, load_companies
from scrapers.snapshot_store import compare, log_change, write_snapshot
from scrapers.tiers import blocker_reason

# Which URL fields should be scraped as static HTML (not behind JS, not an API).
# Newsroom is scraped via RSS when a feed URL is set in the `newsroom_rss` column;
# otherwise it falls back to static HTML.
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
    # Use a per-URL CSS selector if one's configured in the xlsx; else extract
    # the whole body minus nav/header/footer/script (default behaviour).
    selector = c.selectors.get(source)
    res = static_pages.fetch_and_extract(url, selector=selector)
    if not res.ok:
        print(f"  [{c.ticker}/{source}] fetch failed: {res.error}", file=sys.stderr)
        return None
    diff_res = compare(c.ticker, source, res.text)
    if not diff_res.changed:
        return None
    # Always persist the new snapshot so we have a baseline for next run
    write_snapshot(c.ticker, source, res.text)
    # Silent first-run baseline: don't surface "no prior version" entries.
    # They're a setup artifact, not a real content change. Real diffs flow through.
    if "no prior version" in diff_res.diff_text:
        return None
    log_change(c.ticker, source, url, diff_res.diff_text)
    return Change(
        ticker=c.ticker,
        company=c.company,
        source=source,
        url=url,
        summary=_short_summary(diff_res.diff_text, source),
        diff=diff_res.diff_text,
        detected_at=RUN_TS,
    )


def check_edgar(c: Company) -> list[Change]:
    """Detect new SEC filings within the past 7 days."""
    if not c.urls.get("regulatory_filings"):
        return []
    state_key = "edgar_last_accession"
    from scrapers.snapshot_store import _path  # internal helper
    state_path = _path(c.ticker, state_key)
    last_acc = state_path.read_text().strip() if state_path.exists() else None
    try:
        all_filings = edgar.recent_filings(c.ticker)
    except Exception as e:
        print(f"  [{c.ticker}/edgar] error: {e}", file=sys.stderr)
        return []
    if not all_filings:
        return []
    # Always persist the current top accession so subsequent runs can detect
    # new arrivals — even if everything in the past 7 days has been seen.
    if all_filings[0].accession != last_acc:
        write_snapshot(c.ticker, state_key, all_filings[0].accession)
    # Now collect filings to surface: newer than last_acc AND within 7 days.
    new = edgar.new_filings_since(c.ticker, last_acc)
    changes: list[Change] = []
    for f in new:
        rich_desc, materiality = edgar_enrich.summarize(f.form, f.url, f.accession)
        summary = f"[{materiality}] {rich_desc}"
        diff_body = (f"+ Form {f.form} filed {f.filed_date}\n"
                     f"+ {rich_desc}\n"
                     f"+ {f.url}")
        changes.append(Change(
            ticker=c.ticker, company=c.company,
            source=f"edgar:{f.form}",
            url=f.url, summary=summary,
            diff=diff_body,
            detected_at=RUN_TS,
        ))
        log_change(c.ticker, f"edgar:{f.form}", f.url, summary)
    return changes


def check_rss(c: Company, source: str, feed_url: str) -> list[Change]:
    """Fetch RSS feed; emit one Change per new entry. Returns [] if nothing new."""
    try:
        new = rss.new_entries(c.ticker, source, feed_url)
    except Exception as e:
        print(f"  [{c.ticker}/{source}/rss] error: {e}", file=sys.stderr)
        return []
    changes: list[Change] = []
    for entry in new:
        summary = f"{source}: {entry.title}"
        diff_text = f"+ {entry.title}\n+ {entry.link}"
        if entry.published:
            diff_text += f"\n+ Published: {entry.published}"
        if entry.summary:
            diff_text += f"\n+ {entry.summary}"
        changes.append(Change(
            ticker=c.ticker, company=c.company,
            source=f"{source}:rss",
            url=entry.link or feed_url,
            summary=summary[:140],
            diff=diff_text,
            detected_at=RUN_TS,
        ))
        log_change(c.ticker, f"{source}:rss", entry.link or feed_url, diff_text)
    return changes


def process_company(c: Company) -> list[Change]:
    print(f"[{c.ticker}] tier={c.tier} urls={len(c.urls)}")
    found: list[Change] = []

    # Newsroom: prefer RSS if a feed URL is configured
    rss_url = c.urls.get("newsroom_rss")
    if rss_url:
        print(f"  [{c.ticker}/newsroom] using RSS: {rss_url}")
        found.extend(check_rss(c, "newsroom", rss_url))

    for source in STATIC_SOURCES:
        # Skip newsroom HTML scrape if we already handled it via RSS
        if source == "newsroom" and rss_url:
            continue
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
    p.add_argument("--ticker",
                   help="Run for one ticker or comma-separated list "
                        "(e.g. SHOP or SHOP,WIX,DASH); overrides --tier")
    args = p.parse_args()

    companies = load_companies()

    if args.ticker:
        wanted_tickers = {t.strip().upper() for t in args.ticker.split(",") if t.strip()}
        target = [c for c in companies if c.ticker.upper() in wanted_tickers]
        missing = wanted_tickers - {c.ticker.upper() for c in target}
        if missing:
            print(f"Tickers not found: {', '.join(sorted(missing))}", file=sys.stderr)
            return 1
        tier_label = "_".join(sorted(t.ticker.upper().replace(" ", "") for t in target))
    else:
        wanted = {"high"} if args.tier == "high" else (
            {"medium"} if args.tier == "medium" else {"high", "medium"}
        )
        target = [c for c in companies if c.tier in wanted]
        tier_label = args.tier

    # Honor Active flag from xlsx — applies to both --ticker and --tier branches
    target = [c for c in target if c.active]

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
