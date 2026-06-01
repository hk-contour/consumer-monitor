"""Format flagged changes into a morning analyst-friendly digest.

Output structure (top-down, in scan-priority order):
  - Header with date, generation timestamp, counts (total / material / routine)
  - **Material** section: pricing/rate/product/exec/M&A changes, RSS new posts,
    material EDGAR filings (10-K/10-Q/8-K/SC 13G/D/etc.)
  - **Routine** section: section renames, layout shifts, CCPA/GDPR
    boilerplate, insider Form 4/144/etc.

Within each section, entries are grouped by ticker (alphabetical).

Per-change rendering branches by source type:
  - EDGAR (edgar:*): use the already-enriched [MATERIAL]/[ROUTINE]-tagged
    one-liner from edgar_enrich.summarize() — no LLM call needed
  - RSS (foo:rss): treated as MATERIAL by default (press releases are
    publisher-gated content); render structured title + date + snippet
  - Static page (terms, pricing, management_team, …): one LLM call per
    change. The model is instructed to prefix its output with
    [MATERIAL] or [ROUTINE]; we strip the tag for ordering.
"""

from __future__ import annotations

import html
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
    summary: str        # one-line summary from check_*
    diff: str           # unified diff or structured "+..." body
    detected_at: str = ""  # ISO timestamp when our system first saw this change
    company_notes: str = ""  # Analyst Monitoring Notes from the xlsx — passed to LLM


# Tag used internally + on the rendered page
MATERIAL = "MATERIAL"
ROUTINE = "ROUTINE"

# Emoji prefix for visual scanning. Renders consistently on GitHub, in email
# clients, and in browser print-to-PDF output.
ICONS = {MATERIAL: "🔴", ROUTINE: "⚪"}


# -------- diff helpers --------

def _extract_deltas(diff_text: str, cap: int = 8) -> tuple[list[str], list[str]]:
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
    if source.startswith("edgar:"):
        return f"SEC filing ({source.split(':', 1)[1]})"
    if source.endswith(":rss"):
        return source.split(":", 1)[0].replace("_", " ").title() + " (RSS)"
    return source.replace("_", " ").title()


def _fmt_ts(iso_ts: str) -> str:
    """Render '2026-05-28T14:51:38Z' as '2026-05-28 14:51 UTC'."""
    if not iso_ts:
        return ""
    # Be tolerant of minor format variations
    s = iso_ts.replace("Z", "").split(".", 1)[0].replace("T", " ")
    return f"{s[:16]} UTC"


def _strip_materiality_tag(text: str) -> tuple[str | None, str]:
    """Pull `[MATERIAL]` / `[ROUTINE]` prefix from LLM output if present.
    Returns (tag or None, remaining_text)."""
    stripped = text.lstrip()
    for tag in (MATERIAL, ROUTINE):
        prefix = f"[{tag}]"
        if stripped.startswith(prefix):
            return (tag, stripped[len(prefix):].strip())
    return (None, text)


# -------- per-change pre-processing --------

def _classify(c: Change) -> tuple[str, str | None]:
    """Return (materiality, llm_text_or_None).

    For EDGAR/RSS materiality comes from the source itself (no LLM call).
    For static-page sources we make one LLM call here so the result is
    available to BOTH the ordering step and the renderer.
    """
    src = c.source
    if src.startswith("edgar:"):
        # edgar_enrich tagged the summary with [MATERIAL] or [ROUTINE]
        if "[MATERIAL]" in c.summary:
            return (MATERIAL, None)
        return (ROUTINE, None)
    if src.endswith(":rss"):
        return (MATERIAL, None)

    # Static page → ask LLM, with analyst-written Monitoring Notes as context
    llm_text = llm_summarize.summarize(
        ticker=c.ticker, company_name=c.company,
        source=c.source, url=c.url, diff_text=c.diff,
        company_notes=c.company_notes,
    )
    if not llm_text:
        return (MATERIAL, None)  # default-include when LLM unavailable
    tag, remaining = _strip_materiality_tag(llm_text)
    if tag:
        return (tag, remaining)
    # LLM output didn't carry the tag — default MATERIAL, keep raw text
    return (MATERIAL, llm_text)


# -------- per-source renderers --------

def _render_edgar(c: Change, materiality: str, lines: list[str]) -> None:
    # Summary already includes the [MATERIAL]/[ROUTINE] tag; strip for heading
    summary = c.summary
    if summary.startswith("[") and "]" in summary:
        summary = summary[summary.index("]") + 1:].strip()
    icon = ICONS.get(materiality, "")
    lines.append(f"### {icon} {c.ticker} — {_human_source(c.source)}")
    lines.append(f"**{summary}**")
    lines.append("")
    lines.append(f"Source: <{c.url}>")
    if c.detected_at:
        lines.append(f"Detected: {_fmt_ts(c.detected_at)}")
    lines.append("")


def _render_rss(c: Change, materiality: str, lines: list[str]) -> None:
    title = c.summary
    for prefix in (f"{c.source.split(':', 1)[0]}: ",):
        if title.lower().startswith(prefix.lower()):
            title = title[len(prefix):]
            break
    icon = ICONS.get(materiality, "")
    lines.append(f"### {icon} {c.ticker} — {_human_source(c.source)}")
    lines.append(f"**{title}**")
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
    if c.detected_at:
        lines.append(f"Detected: {_fmt_ts(c.detected_at)}")
    lines.append("")


def _render_static(c: Change, materiality: str, llm_text: str | None,
                   lines: list[str]) -> None:
    icon = ICONS.get(materiality, "")
    lines.append(f"### {icon} {c.ticker} — {_human_source(c.source)}")
    if llm_text:
        lines.append(f"**What it means:** {llm_text}")
        lines.append("")
    else:
        lines.append(f"**Summary:** {c.summary}")
        lines.append("")
    added, removed = _extract_deltas(c.diff, cap=10)
    if added or removed:
        lines.append("**Detail:**")
        # Wrap in a `diff` fenced block so GitHub renders + lines green
        # and - lines red. Carries through to browser print-to-PDF.
        lines.append("```diff")
        if removed:
            for r in removed:
                lines.append(f"- {r[:200]}")
        if added:
            for a in added:
                lines.append(f"+ {a[:200]}")
        lines.append("```")
        lines.append("")
    lines.append(f"Source: <{c.url}>")
    if c.detected_at:
        lines.append(f"Detected: {_fmt_ts(c.detected_at)}")
    lines.append("")


def _render_change(c: Change, materiality: str, llm_text: str | None,
                   lines: list[str]) -> None:
    if c.source.startswith("edgar:"):
        _render_edgar(c, materiality, lines)
    elif c.source.endswith(":rss"):
        _render_rss(c, materiality, lines)
    else:
        _render_static(c, materiality, llm_text, lines)


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

    # Pre-classify every change once. This is also where LLM calls happen
    # for static-page sources; cached so re-runs are cheap.
    classified: list[tuple[Change, str, str | None]] = [
        (c, *_classify(c)) for c in changes
    ]
    material = [t for t in classified if t[1] == MATERIAL]
    routine = [t for t in classified if t[1] == ROUTINE]

    lines.append(
        f"**{len(changes)} flagged changes** — "
        f"{len(material)} material, {len(routine)} routine."
    )
    if not llm_summarize.is_available():
        lines.append("")
        lines.append("_Note: LLM interpretation disabled "
                     "(ANTHROPIC_API_KEY not set). Showing basic summaries; "
                     "all static-page items default to material._")
    lines.append("")
    lines.append("---")
    lines.append("")

    def emit_section(label: str, items: list, empty_msg: str) -> None:
        lines.append(f"## {label} ({len(items)})")
        lines.append("")
        if not items:
            lines.append(empty_msg)
            lines.append("")
            return
        # Group by ticker, alphabetical
        by_ticker: dict[str, list] = {}
        for tup in items:
            by_ticker.setdefault(tup[0].ticker, []).append(tup)
        for ticker in sorted(by_ticker):
            for c, materiality, llm_text in by_ticker[ticker]:
                _render_change(c, materiality, llm_text, lines)

    emit_section(f"{ICONS[MATERIAL]} Material", material,
                 "_No material changes this run._")
    lines.append("---")
    lines.append("")
    emit_section(f"{ICONS[ROUTINE]} Routine", routine,
                 "_No routine changes this run._")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Also emit a parallel .html with inline-styled diff blocks. Browser
    # print-to-PDF on this file produces a colored PDF without depending on
    # GitHub's page CSS or the user's "Background graphics" toggle.
    write_digest_html(today, tier_label, material, routine)

    return out


# -------- HTML render (parallel to the markdown above) --------

HTML_STYLE = """\
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
       max-width: 800px; margin: 40px auto; padding: 0 24px; color: #1f2328;
       line-height: 1.5; }
h1 { border-bottom: 1px solid #d0d7de; padding-bottom: 8px; margin-top: 24px; }
h2 { border-bottom: 1px solid #d0d7de; padding-bottom: 6px; margin-top: 36px; }
h3 { margin-top: 28px; }
.material { color: #cf222e; }
.routine  { color: #6e7781; }
.meta     { color: #6e7781; font-size: 14px; margin-top: 4px; }
.what     { margin: 12px 0; }
.detail-block { border: 1px solid #d0d7de; border-radius: 6px; padding: 0;
                font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
                font-size: 13px; line-height: 1.45; margin: 12px 0;
                overflow: hidden; }
.detail-block div { padding: 4px 12px; white-space: pre-wrap; word-break: break-word; }
.detail-block .added   { background: #e6ffec; color: #0a3622; }
.detail-block .removed { background: #ffebe9; color: #82071e; }
a { color: #0969da; text-decoration: none; }
a:hover { text-decoration: underline; }
hr { border: 0; border-top: 1px solid #d0d7de; margin: 32px 0; }
.summary-bar { font-size: 16px; margin: 16px 0; }
.section-count { color: #6e7781; font-weight: normal; font-size: 0.85em; }
"""


def _html_escape(s: str) -> str:
    return html.escape(s, quote=False)


def _html_entry(c: Change, materiality: str, llm_text: str | None) -> str:
    icon_color = "material" if materiality == MATERIAL else "routine"
    icon = ICONS.get(materiality, "")
    header = (
        f'<h3><span class="{icon_color}">{icon}</span> '
        f'{_html_escape(c.ticker)} — {_html_escape(_human_source(c.source))}</h3>\n'
    )

    body_parts: list[str] = []

    if c.source.startswith("edgar:"):
        summary = c.summary
        if summary.startswith("[") and "]" in summary:
            summary = summary[summary.index("]") + 1:].strip()
        body_parts.append(f'<p class="what"><strong>{_html_escape(summary)}</strong></p>')

    elif c.source.endswith(":rss"):
        title = c.summary
        for prefix in (f"{c.source.split(':', 1)[0]}: ",):
            if title.lower().startswith(prefix.lower()):
                title = title[len(prefix):]
                break
        body_parts.append(f'<p class="what"><strong>{_html_escape(title)}</strong></p>')
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
            body_parts.append(f'<p class="meta">Published {_html_escape(published)}</p>')
        if snippet:
            sn = snippet[:400] + ("…" if len(snippet) > 400 else "")
            body_parts.append(f'<p>{_html_escape(sn)}</p>')

    else:  # static
        if llm_text:
            body_parts.append(
                f'<p class="what"><strong>What it means:</strong> '
                f'{_html_escape(llm_text)}</p>'
            )
        else:
            body_parts.append(
                f'<p class="what"><strong>Summary:</strong> {_html_escape(c.summary)}</p>'
            )
        added, removed = _extract_deltas(c.diff, cap=10)
        if added or removed:
            block: list[str] = ['<div class="detail-block">']
            for r in removed:
                block.append(f'<div class="removed">− {_html_escape(r[:200])}</div>')
            for a in added:
                block.append(f'<div class="added">+ {_html_escape(a[:200])}</div>')
            block.append("</div>")
            body_parts.append("\n".join(block))

    meta_lines = [f'<a href="{_html_escape(c.url)}">{_html_escape(c.url)}</a>']
    if c.detected_at:
        meta_lines.append(f"Detected: {_html_escape(_fmt_ts(c.detected_at))}")
    body_parts.append(
        '<p class="meta">' + "<br>".join(meta_lines) + "</p>"
    )

    return header + "\n".join(body_parts) + "\n"


def write_digest_html(today: str, tier_label: str,
                      material: list, routine: list) -> Path:
    out = OUTPUT_DIR / f"{today}_{tier_label}.html"
    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en"><head>')
    parts.append('<meta charset="utf-8">')
    parts.append(f"<title>Morning digest — {today}</title>")
    parts.append(f"<style>{HTML_STYLE}</style>")
    parts.append("</head><body>")
    parts.append(f"<h1>Morning digest — {today}</h1>")
    parts.append(
        f'<p class="meta">Generated '
        f'{time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}.</p>'
    )
    total = len(material) + len(routine)
    parts.append(
        f'<p class="summary-bar"><strong>{total} flagged changes</strong> — '
        f'<span class="material">{len(material)} material</span>, '
        f'<span class="routine">{len(routine)} routine</span>.</p>'
    )
    parts.append("<hr>")

    def emit_section(label: str, items: list, color_class: str,
                     empty_msg: str) -> None:
        parts.append(
            f'<h2><span class="{color_class}">{ICONS[label]}</span> {label} '
            f'<span class="section-count">({len(items)})</span></h2>'
        )
        if not items:
            parts.append(f"<p><em>{empty_msg}</em></p>")
            return
        by_ticker: dict[str, list] = {}
        for tup in items:
            by_ticker.setdefault(tup[0].ticker, []).append(tup)
        for ticker in sorted(by_ticker):
            for c, materiality, llm_text in by_ticker[ticker]:
                parts.append(_html_entry(c, materiality, llm_text))

    emit_section("MATERIAL", material, "material",
                 "No material changes this run.")
    parts.append("<hr>")
    emit_section("ROUTINE", routine, "routine",
                 "No routine changes this run.")
    parts.append("</body></html>")

    out.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return out
