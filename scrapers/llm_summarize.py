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

PROMPT = """You are summarizing a website diff for a hedge fund analyst monitoring \
consumer/fintech/marketplace companies. In ONE or TWO sentences total, describe:
(1) what specifically changed (numeric values, text, headings), and
(2) whether it looks material (pricing/rate/product change, new disclosure) or \
routine (typo, layout shuffle, date stamp, section rename).

Be specific. No speculation. No padding. No greeting. No bullet points. \
Just the 1-2 sentence summary.

Company: {ticker} ({company_name})
Page type: {source}
Page URL: {url}

Detected change (unified diff):
{diff_text}

Summary:"""


def is_available() -> bool:
    return bool(API_KEY)


def summarize(ticker: str, company_name: str, source: str, url: str,
              diff_text: str) -> str | None:
    """Return a 1-2 sentence summary of the diff, or None if unavailable / error.

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
    cache_key = hashlib.sha256(
        f"{ticker}|{source}|{diff_text}".encode("utf-8")
    ).hexdigest()[:16]
    cache_file = CACHE_DIR / f"{cache_key}.txt"
    if cache_file.exists():
        try:
            return cache_file.read_text(encoding="utf-8").strip() or None
        except OSError:
            pass

    prompt = PROMPT.format(
        ticker=ticker, company_name=company_name,
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
