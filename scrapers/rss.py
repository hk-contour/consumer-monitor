"""RSS scraper.

Pattern: fetch feed body with requests (so cookies/UA work), parse with
feedparser, dedup against stored GUID set, emit new entries.

GUIDs are persisted per (ticker, source) in snapshots/<TICKER>/<source>.guids
— one GUID per line. Subsequent runs only emit entries whose GUID is new.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
from dateutil import parser as dateparser

from .static_pages import USER_AGENT

MAX_AGE_DAYS = 7  # Only emit entries published within this window

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = ROOT / "snapshots"


@dataclass
class FeedEntry:
    title: str
    link: str
    guid: str
    published: str
    summary: str


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def _guid_path(ticker: str, source: str) -> Path:
    return SNAPSHOT_DIR / _safe(ticker) / f"{_safe(source)}.guids"


def _load_seen(ticker: str, source: str) -> set[str]:
    p = _guid_path(ticker, source)
    if not p.exists():
        return set()
    return {ln.strip() for ln in p.read_text().splitlines() if ln.strip()}


def _save_seen(ticker: str, source: str, guids: set[str]) -> None:
    p = _guid_path(ticker, source)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Cap at 500 most-recent to keep the file small
    p.write_text("\n".join(sorted(guids)[-500:]))


def fetch_feed(url: str, timeout: int = 30) -> list[FeedEntry]:
    """Fetch and parse a feed. Returns all entries (no dedup)."""
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    out: list[FeedEntry] = []
    for e in feed.entries:
        guid = e.get("id") or e.get("guid") or e.get("link", "")
        out.append(FeedEntry(
            title=e.get("title", "").strip(),
            link=e.get("link", "").strip(),
            guid=str(guid).strip(),
            published=e.get("published", e.get("updated", "")),
            summary=re.sub(r"<[^>]+>", "", e.get("summary", ""))[:500],
        ))
    return out


def _is_recent(published_str: str, max_age_days: int) -> bool:
    """True if the published timestamp is within max_age_days of now.

    Drops entries with no parseable date (safer to omit than misdate).
    """
    if not published_str:
        return False
    try:
        dt = dateparser.parse(published_str)
    except (ValueError, TypeError):
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= datetime.now(timezone.utc) - timedelta(days=max_age_days)


def new_entries(ticker: str, source: str, url: str,
                max_age_days: int = MAX_AGE_DAYS) -> list[FeedEntry]:
    """Fetch feed and return entries that are (a) within max_age_days AND
    (b) not in the stored GUID set.

    First-run behavior: emit all recent (past N days) entries. There's no
    "silent first run" here because each entry has its own publish date —
    a 5-day-old press release is real signal, not a baselining artifact.
    """
    entries = fetch_feed(url)
    entries = [e for e in entries if _is_recent(e.published, max_age_days)]
    seen = _load_seen(ticker, source)
    new = [e for e in entries if e.guid and e.guid not in seen]
    if new:
        seen.update(e.guid for e in new)
        _save_seen(ticker, source, seen)
    return new
