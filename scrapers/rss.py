"""RSS scraper.

Pattern: fetch feed body with requests (so cookies/UA work), parse with
feedparser, dedup against stored GUID set, emit new entries.

GUIDs are persisted per (ticker, source) in snapshots/<TICKER>/<source>.guids
— one GUID per line. Subsequent runs only emit entries whose GUID is new.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import feedparser
import requests

from .static_pages import USER_AGENT

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


def new_entries(ticker: str, source: str, url: str,
                first_run_limit: int = 5) -> list[FeedEntry]:
    """Fetch feed and return only entries we haven't seen.

    On first run (no stored GUIDs), emit up to `first_run_limit` newest
    entries as a baseline — matches EDGAR scraper behavior.
    """
    entries = fetch_feed(url)
    seen = _load_seen(ticker, source)
    if not seen:
        # First run: take the most-recent N, mark all as seen
        new = entries[:first_run_limit]
        _save_seen(ticker, source, {e.guid for e in entries if e.guid})
        return new
    new = [e for e in entries if e.guid and e.guid not in seen]
    if new:
        seen.update(e.guid for e in new)
        _save_seen(ticker, source, seen)
    return new
