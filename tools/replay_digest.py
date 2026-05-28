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
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from digest import Change, write_digest  # noqa: E402
from scrapers.config_reader import load_companies  # noqa: E402
from scrapers.edgar import MAX_AGE_DAYS as EDGAR_MAX_AGE  # noqa: E402
from scrapers.static_pages import _is_binary_url  # noqa: E402

CHANGELOG = ROOT / "changelog.jsonl"
# Match any YYYY-MM-DD that appears in the changelog diff field. For EDGAR
# the first such date is the transaction/filing date (≈ same day for Form 4/144).
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


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
    print(f"EDGAR filter: filed date within past {EDGAR_MAX_AGE} days")

    edgar_cutoff = datetime.now(timezone.utc) - timedelta(days=EDGAR_MAX_AGE)

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
            diff = entry.get("diff", "")
            source = entry["source"]
            # Skip first-run baselines — they have no real content to interpret
            if "no prior version" in diff or "new snapshot" in diff:
                continue
            # Skip entries with no actual diff body (just a short note)
            if len(diff.strip()) < 40:
                continue
            # Skip binary-URL entries (PDFs etc.) — the live system now
            # refuses these; the replay should match.
            if _is_binary_url(entry.get("url", "")):
                continue
            # For EDGAR: enforce the same filed-date window the live system uses
            if source.startswith("edgar:"):
                m = DATE_RE.search(diff)
                if not m:
                    continue  # can't verify date → skip rather than misrepresent
                try:
                    filed = datetime.strptime(m.group(1), "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    continue
                if filed < edgar_cutoff:
                    continue
            key = (entry["ticker"], source, entry.get("url", ""))
            if key in seen_keys:
                continue
            seen_keys.add(key)

            # Reconstruct summary correctly per source type:
            #  - EDGAR: changelog "diff" field stores the rich one-liner
            #    (e.g. "[ROUTINE] Insider trade — Tony Xu sold ..."). Use it
            #    as the summary; the digest's _render_edgar will format it.
            #  - RSS:   diff body has "+ title / + link / + Published / + summary".
            #    Extract title from the first "+ " line.
            #  - Static: leave a generic "change detected" — LLM interprets
            #    from the diff body.
            if source.startswith("edgar:"):
                summary = diff
                diff = f"+ {diff}\n+ {entry.get('url', '')}"
            elif source.endswith(":rss"):
                first_plus = next(
                    (ln[2:].strip() for ln in diff.splitlines()
                     if ln.startswith("+ ") and not ln[2:].startswith("http")),
                    "",
                )
                kind = source.split(":", 1)[0]
                summary = f"{kind}: {first_plus}" if first_plus else f"{source}: change detected"
            else:
                summary = f"{source}: change detected"

            changes.append(Change(
                ticker=entry["ticker"],
                company=c.company,
                source=source,
                url=entry.get("url", ""),
                summary=summary,
                diff=diff,
            ))

    print(f"Reconstructed {len(changes)} unique changes")
    out = write_digest(changes, label)
    print(f"Sample digest written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
