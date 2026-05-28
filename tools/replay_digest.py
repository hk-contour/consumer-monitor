"""Replay past changelog entries through the current digest writer.

Useful for generating a polished sample digest showcasing the
LLM-interpreted format on real historical data — no need to wait for
new world events.

Configured via env:
  REPLAY_SINCE   ISO timestamp; only replay entries newer than this
                 (default: 24h ago)
  REPLAY_LABEL   Filename label for the digest (default: SAMPLE)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from digest import Change, write_digest  # noqa: E402
from scrapers.config_reader import load_companies  # noqa: E402

CHANGELOG = ROOT / "changelog.jsonl"


def main() -> int:
    since_str = os.environ.get("REPLAY_SINCE", "").strip()
    if since_str:
        since = since_str
    else:
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    label = os.environ.get("REPLAY_LABEL", "SAMPLE").strip() or "SAMPLE"

    print(f"Replaying changelog entries since {since}")
    print(f"Output label: {label}")

    cos = {c.ticker: c for c in load_companies()}

    seen_keys: set[tuple[str, str, str]] = set()  # dedup repeats
    changes: list[Change] = []
    with CHANGELOG.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("ts", "") < since:
                continue
            c = cos.get(entry["ticker"])
            if c is None:
                continue
            key = (entry["ticker"], entry["source"], entry.get("url", ""))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            changes.append(Change(
                ticker=entry["ticker"],
                company=c.company,
                source=entry["source"],
                url=entry.get("url", ""),
                summary=f"{entry['source']}: change detected",
                diff=entry.get("diff", ""),
            ))

    print(f"Reconstructed {len(changes)} unique changes")
    out = write_digest(changes, label)
    print(f"Sample digest written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
