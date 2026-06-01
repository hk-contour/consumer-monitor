"""LLM-based per-change interpretation, called from digest.write_digest.

Sends a single Anthropic API call per flagged change, gets back a 1-2
sentence analyst-style summary, caches by diff-hash. Cost discipline:

- Only invoked at digest-write time (never in the inner scrape loop).
- Skipped entirely when ANTHROPIC_API_KEY is unset → falls back to the
  basic summary already in the Change.summary field.
- Results cached on disk at snapshots/_llm_cache/<hash>.txt; identical
  diffs on subsequent runs hit cache, no API call.
- Capped prompt size (4 KB diff) to bound per-call cost.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import requests

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
MODEL = (os.environ.get("CLAUDE_MODEL", "").strip()
         or "claude-haiku-4-5")
API_URL = "https://api.anthropic.com/v1/messages"
CACHE_DIR = Path(__file__).resolve().parent.parent / "snapshots" / "_llm_cache"

PROMPT_VERSION = "v3-with-notes"

PROMPT = """You are summarizing a website diff for a hedge fund analyst monitoring \
consumer/fintech/marketplace companies. The analyst will scan dozens of items \
each morning and needs to know IMMEDIATELY whether to read closely or skip.

Output EXACTLY this format (one line, then optional second sentence):
[MATERIAL] Sentence describing the change.
  — OR —
[ROUTINE] Sentence describing the change.

Begin with [MATERIAL] (brackets, all caps) if the change involves:
- A pricing, rate, or fee change
- A new product, plan, or major feature
- An exec hire or departure
- A partnership, M&A, regulatory action
- A change to a quantitative operating metric (e.g. catalog size, store count)
- Anything the analyst's monitoring notes (below) specifically flag as relevant

Begin with [ROUTINE] if the change is:
- A section rename or layout shift
- A date-stamp refresh ("accurate as of …")
- CCPA/GDPR/cookie boilerplate
- A typo or formatting fix
- Pure rotation of news posts on a feed page
- PDF re-encoding, image swaps, link reorderings

After the bracket, write 1-2 sentences of specific factual description. \
No speculation. No greeting. No padding.

Company: {ticker} ({company_name})
{notes_section}Page type: {source}
Page URL: {url}

Detected change (unified diff):
{diff_text}

Summary:"""


def is_available() -> bool:
    return bool(API_KEY)


def summarize(ticker: str, company_name: str, source: str, url: str,
              diff_text: str, company_notes: str = "") -> str | None:
    """Return a 1-2 sentence summary of the diff, or None if unavailable / error.

    `company_notes` is analyst-written guidance from the xlsx (the
    Monitoring Notes column). Threaded into the prompt so the LLM has
    company-specific context — e.g. for SHOP, "Monitor changelog.shopify.com;
    App Store changes signal platform strategy" lets the model upweight those
    signals as material.

    Falls back silently to None on any error — callers should treat None as
    "no enrichment available" and render the existing Change.summary field.
    """
    if not API_KEY:
        # One-time loud warning so misconfig is obvious in workflow logs
        if not getattr(summarize, "_warned_no_key", False):
            print("  [llm] ANTHROPIC_API_KEY not set — falling back to "
                  "basic summaries", file=sys.stderr)
            summarize._warned_no_key = True  # type: ignore[attr-defined]
        return None
    if not diff_text:
        return None

    diff_text = diff_text[:4000]  # cap prompt
    notes_section = (
        f"Analyst monitoring notes for this company: {company_notes.strip()}\n"
        if company_notes else ""
    )
    # PROMPT_VERSION + notes included in cache key so prompt changes invalidate
    # cache cleanly AND per-company notes are reflected in the cached response.
    cache_key = hashlib.sha256(
        f"{PROMPT_VERSION}|{ticker}|{source}|{notes_section}|{diff_text}".encode("utf-8")
    ).hexdigest()[:16]
    cache_file = CACHE_DIR / f"{cache_key}.txt"
    if cache_file.exists():
        try:
            return cache_file.read_text(encoding="utf-8").strip() or None
        except OSError:
            pass

    prompt = PROMPT.format(
        ticker=ticker, company_name=company_name,
        notes_section=notes_section,
        source=source, url=url, diff_text=diff_text,
    )

    try:
        r = requests.post(
            API_URL, timeout=30,
            headers={
                "x-api-key": API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODEL,
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
    except requests.RequestException as e:
        print(f"  [llm/{ticker}/{source}] request failed: {e}", file=sys.stderr)
        return None

    if r.status_code != 200:
        # Surface the failure so we can debug — body usually tells us why
        print(f"  [llm/{ticker}/{source}] HTTP {r.status_code}: "
              f"{r.text[:300]}", file=sys.stderr)
        return None
    try:
        text = r.json()["content"][0]["text"].strip()
    except (KeyError, IndexError, ValueError) as e:
        print(f"  [llm/{ticker}/{source}] parse error: {e}; "
              f"body: {r.text[:300]}", file=sys.stderr)
        return None

    if not text:
        return None
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        cache_file.write_text(text, encoding="utf-8")
    except OSError:
        pass
    return text
