"""POST the latest digest to a Power Automate webhook, which emails it.

Designed to run as the final step of the monitor workflow. Reads two env vars:

  EMAIL_WEBHOOK_URL  — the Power Automate "When an HTTP request is received" URL
  EMAIL_TO           — comma/semicolon-separated recipient list

The Flow is expected to accept a JSON body of the shape:

  { "subject": "...", "to": "a@x.com;b@y.com", "html": "<html>…</html>" }

and wire those into a "Send an email (V2)" action (To / Subject / Body, with
"Is HTML" on). Nothing here touches Outlook directly, so no Entra app or SMTP
credential is involved — the Flow sends from the connected mailbox.

Exit codes: 0 = sent or nothing-to-do (missing config is a soft skip so the
workflow doesn't fail); 1 = a real send error worth surfacing.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIGEST_DIR = ROOT / "monitoring_system"


def _latest_html() -> Path | None:
    """Newest digest .html for today; fall back to newest overall."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    todays = sorted(DIGEST_DIR.glob(f"{today}_*.html"),
                    key=lambda p: p.stat().st_mtime)
    if todays:
        return todays[-1]
    allhtml = sorted(DIGEST_DIR.glob("*.html"), key=lambda p: p.stat().st_mtime)
    return allhtml[-1] if allhtml else None


def _counts(md_path: Path) -> str:
    """Pull the '**N flagged changes** — X material, Y routine.' line for the subject."""
    if not md_path.exists():
        return ""
    for line in md_path.read_text(encoding="utf-8").splitlines():
        m = re.search(r"\*\*(\d+) flagged changes\*\*\s*—\s*(\d+) material", line)
        if m:
            total, material = m.group(1), m.group(2)
            return f"{total} changes, {material} material"
    return ""


def main() -> int:
    webhook = os.environ.get("EMAIL_WEBHOOK_URL", "").strip()
    to = os.environ.get("EMAIL_TO", "").strip().replace(",", ";")
    if not webhook:
        print("EMAIL_WEBHOOK_URL not set — skipping email.")
        return 0
    if not to:
        print("EMAIL_TO not set — skipping email.")
        return 0

    html_path = _latest_html()
    if html_path is None:
        print("No digest .html found — nothing to send.")
        return 0
    html = html_path.read_text(encoding="utf-8")

    date = html_path.name.split("_", 1)[0]
    counts = _counts(html_path.with_suffix(".md"))
    subject = f"Consumer Monitor — Morning digest {date}"
    if counts:
        subject += f" ({counts})"

    payload = json.dumps({"subject": subject, "to": to, "html": html}).encode("utf-8")
    req = urllib.request.Request(
        webhook, data=payload,
        headers={"Content-Type": "application/json"}, method="POST")

    last_err = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                print(f"Sent '{subject}' to {to} via webhook "
                      f"(HTTP {resp.status}, {html_path.name}).")
                return 0
        except urllib.error.HTTPError as e:
            # Surface the response body — Power Automate returns a JSON error
            # explaining a 4xx (schema/validation mismatch at the trigger).
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:1000]
            except Exception:  # noqa: BLE001
                pass
            last_err = f"HTTP {e.code} {e.reason} — {body}"
            if 400 <= e.code < 500:
                break  # client-side; retrying won't help
            time.sleep(2 ** attempt)
        except Exception as e:  # noqa: BLE001 — transport/timeout
            last_err = str(e)
            time.sleep(2 ** attempt)
    print(f"Email send failed: {last_err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
