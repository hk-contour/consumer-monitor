"""Snapshot storage and diffing.

Store extracted clean text per (ticker, source_type) as plain files under snapshots/.
On each fetch:
  1. Hash the new text (SHA-256).
  2. If hash matches the prior snapshot, no change — return None.
  3. If different, generate a unified diff and return it.
  4. Caller is responsible for overwriting the snapshot file and logging to changelog.

Git history of snapshots/ is the changelog archive.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = ROOT / "snapshots"
CHANGELOG = ROOT / "changelog.jsonl"

MIN_DIFF_CHARS = 80  # ignore tiny diffs — noise floor from the briefing


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def _path(ticker: str, source_type: str) -> Path:
    return SNAPSHOT_DIR / _safe(ticker) / f"{_safe(source_type)}.txt"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class DiffResult:
    changed: bool
    diff_text: str = ""
    old_hash: str = ""
    new_hash: str = ""


def compare(ticker: str, source_type: str, new_text: str) -> DiffResult:
    """Compare new_text against stored snapshot. Does NOT write."""
    path = _path(ticker, source_type)
    new_hash = sha256(new_text)
    if not path.exists():
        return DiffResult(changed=True, diff_text="(new snapshot — no prior version)",
                          old_hash="", new_hash=new_hash)
    old_text = path.read_text(encoding="utf-8")
    old_hash = sha256(old_text)
    if old_hash == new_hash:
        return DiffResult(changed=False, old_hash=old_hash, new_hash=new_hash)

    diff_lines = list(difflib.unified_diff(
        old_text.splitlines(),
        new_text.splitlines(),
        fromfile=f"{ticker}/{source_type} (prior)",
        tofile=f"{ticker}/{source_type} (new)",
        lineterm="",
        n=2,
    ))
    diff_text = "\n".join(diff_lines)
    if len(diff_text) < MIN_DIFF_CHARS:
        return DiffResult(changed=False, old_hash=old_hash, new_hash=new_hash)

    return DiffResult(changed=True, diff_text=diff_text,
                      old_hash=old_hash, new_hash=new_hash)


def write_snapshot(ticker: str, source_type: str, new_text: str) -> Path:
    path = _path(ticker, source_type)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    return path


def log_change(ticker: str, source_type: str, url: str, diff_text: str) -> None:
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ticker": ticker,
        "source": source_type,
        "url": url,
        "diff": diff_text[:4000],  # cap to keep jsonl readable
    }
    with CHANGELOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
