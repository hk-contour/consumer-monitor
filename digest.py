"""Format flagged changes into a morning analyst-friendly digest.

Format goals (per build conversation):
- One-line "what it means" interpretation per change, not raw diff syntax
- Group by ticker, then by source
- Plain prose, no `+`/`-`/`@@` markers in user-facing text
- Renders well as Markdown on GitHub AND as plain-ish text in email clients
- Source URL always visible

Per-change rendering branches by source type:
- EDGAR (edgar:*): summary already enriched by edgar_enrich.summarize() —
  use it verbatim, no LLM call needed
- RSS (foo:rss): summary is the entry title, diff has title+date+snippet
  pre-formatted — render structured fields, no LLM call needed
- Static page (terms/pricing/management_team/etc.): use llm_summarize
  for the "what it means" line, and emit a short Detail block listing
  the actual delta lines (not the full unified diff)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from scrapers import llm_summarize

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "monitoring_system"


@dataclass
class Change:
    ticker: str
    company: str
    source: str         # e.g. "pricing", "terms", "edgar:10-Q", "newsroom:rss"
    url: str
    summary: str        # one-line summary (from check_*)
    diff: str           # unified diff or structured "+..." body


# -------- diff helpers --------

def _extract_deltas(diff_text: str, cap: int = 8) -> tuple[list[str], list[str]]:
    """Pull the actual +/- content lines from a unified diff, skipping
    headers (---/+++/@@) and context lines. Returns (added, removed)."""
    added: list[str] = []
    removed: list[str] = []
    for ln in diff_text.splitlines():
        if ln.startswith("+++") or ln.startswith("---") or ln.startswith("@@"):
            continue
        if ln.startswith("+"):
            content = ln[1:].strip()
            if content:
                added.append(content)
        elif ln.startswith("-"):
            content = ln[1:].strip()
            if content:
                removed.append(content)
    return added[:cap], removed[:cap]


def _human_source(source: str) -> str:
    """Render an internal source key as a display label."""
    if source.startswith("edgar:"):
        return f"SEC filing ({source.split(':', 1)[1]})"
    if source.endswith(":rss"):
        return source.split(":", 1)[0].replace("_", " ").title() + " (RSS)"
    return source.replace("_", " ").title()


# -------- per-source renderers --------

def _render_edgar(c: Change, lines: list[str]) -> None:
    """EDGAR entries already have a rich one-liner from edgar_enrich.
    The Change.summary is like '[ROUTINE] Insider trade — Tony Xu (CEO) sold ...'
    Just present it cleanly."""
    # Strip the leading [MATERIAL]/[ROUTINE] tag for the heading
    summary = c.summary
    tag = ""
    if summary.startswith("[") and "]" in summary:
        end = summary.index("]")
        tag = summary[:end + 1]
        summary = summary[end + 1:].strip()

    lines.append(f"### {_human_source(c.source)} {tag}".rstrip())
    lines.append(f"**{summary}**")
    lines.append("")
    lines.append(f"Source: <{c.url}>")
    lines.append("")


def _render_rss(c: Change, lines: list[str]) -> None:
    """RSS entries: title (already in summary), published date + snippet
    are in the diff body. Render as clean prose."""
    # Strip "newsroom: " prefix from summary if present
    title = c.summary
    for prefix in (f"{c.source.split(':', 1)[0]}: ",):
        if title.lower().startswith(prefix.lower()):
            title = title[len(prefix):]
            break

    lines.append(f"### {_human_source(c.source)} — {title}")
    # Diff body for RSS contains: + title / + link / + Published: ... / + summary
    # Pull the Published + summary lines for clean display
    published = None
    snippet = None
    for ln in c.diff.splitlines():
        if ln.startswith("+ Published:"):
            published = ln[12:].strip()
        elif ln.startswith("+ ") and ln[2:].strip() and not (
            ln[2:].startswith("http") or ln[2:].strip() == title
        ):
            if snippet is None:
                snippet = ln[2:].strip()
    if published:
        lines.append(f"_Published {published}_")
    if snippet:
        lines.append("")
        lines.append(snippet[:400] + ("…" if len(snippet) > 400 else ""))
    lines.append("")
    lines.append(f"Source: <{c.url}>")
    lines.append("")


def _render_static(c: Change, lines: list[str]) -> None:
    """Static-page diffs: ask LLM for a 1-2 sentence interpretation, then
    show the actual delta lines (added/removed content) as supporting detail.
    Skips the LLM call gracefully if ANTHROPIC_API_KEY is not configured."""
    lines.append(f"### {_human_source(c.source)} — change detected")

    interp = llm_summarize.summarize(
        ticker=c.ticker, company_name=c.company,
        source=c.source, url=c.url, diff_text=c.diff,
    )
    if interp:
        lines.append(f"**What it means:** {interp}")
        lines.append("")
    else:
        # Fallback: use the existing one-line summary from check_static_url
        lines.append(f"**Summary:** {c.summary}")
        lines.append("")

    added, removed = _extract_deltas(c.diff, cap=10)
    if added or removed:
        lines.append("**Detail:**")
        if removed:
            for r in removed:
                lines.append(f"  − {r[:200]}")
        if added:
            for a in added:
                lines.append(f"  + {a[:200]}")
        lines.append("")

    lines.append(f"Source: <{c.url}>")
    lines.append("")


def _render_change(c: Change, lines: list[str]) -> None:
    if c.source.startswith("edgar:"):
        _render_edgar(c, lines)
    elif c.source.endswith(":rss"):
        _render_rss(c, lines)
    else:
        _render_static(c, lines)


# -------- top-level digest --------

def write_digest(changes: list[Change], tier_label: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = time.strftime("%Y-%m-%d")
    fname = f"{today}_{tier_label}.md"
    out = OUTPUT_DIR / fname

    lines: list[str] = []
    lines.append(f"# Morning digest — {today}")
    lines.append("")
    lines.append(f"Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}.")

    if not changes:
        lines.append("")
        lines.append("**No changes detected this run.**")
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out

    # Top-level summary: tickers + count
    by_ticker: dict[str, list[Change]] = {}
    for c in changes:
        by_ticker.setdefault(c.ticker, []).append(c)
    ticker_summary = ", ".join(
        f"{t} ({len(items)})" for t, items in sorted(by_ticker.items())
    )
    lines.append(f"**{len(changes)} flagged changes** — {ticker_summary}")
    if not llm_summarize.is_available():
        lines.append("")
        lines.append("_Note: LLM interpretation is disabled "
                     "(ANTHROPIC_API_KEY not set). Showing basic summaries only._")
    lines.append("")
    lines.append("---")
    lines.append("")

    for ticker, items in sorted(by_ticker.items()):
        company = items[0].company
        lines.append(f"## {ticker} — {company}")
        lines.append("")
        for c in items:
            _render_change(c, lines)
        lines.append("---")
        lines.append("")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
