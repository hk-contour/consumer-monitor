"""Format flagged changes into a morning markdown digest."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "monitoring_system"


@dataclass
class Change:
    ticker: str
    company: str
    source: str         # e.g. "pricing", "terms", "edgar:10-Q"
    url: str
    summary: str        # one-line summary
    diff: str           # unified diff snippet


def write_digest(changes: list[Change], tier_label: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = time.strftime("%Y-%m-%d")
    fname = f"{today}_{tier_label}.md"
    out = OUTPUT_DIR / fname

    lines: list[str] = []
    lines.append(f"# Morning digest — {today} ({tier_label})")
    lines.append("")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    lines.append(f"Flagged changes: {len(changes)}")
    lines.append("")

    if not changes:
        lines.append("_No changes detected this run._")
    else:
        # Group by ticker
        by_ticker: dict[str, list[Change]] = {}
        for c in changes:
            by_ticker.setdefault(c.ticker, []).append(c)
        for ticker, items in sorted(by_ticker.items()):
            company = items[0].company
            lines.append(f"## {ticker} — {company}")
            lines.append("")
            for c in items:
                lines.append(f"### {c.source}")
                lines.append(f"- URL: {c.url}")
                lines.append(f"- Summary: {c.summary}")
                lines.append("")
                lines.append("```diff")
                lines.append(c.diff[:3000])
                lines.append("```")
                lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    return out
