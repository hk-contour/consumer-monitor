"""Smoke test for the LLM summarizer. Runs one hard-coded diff through
scrapers.llm_summarize.summarize() and prints the result. Useful to
verify ANTHROPIC_API_KEY / CLAUDE_MODEL / network are all wired correctly,
independent of whether the scraper has any real diffs to summarize.

Exits 0 on success (even if LLM returns None — that's a warning, not error).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scrapers import llm_summarize  # noqa: E402

print(f"ANTHROPIC_API_KEY set: {bool(os.environ.get('ANTHROPIC_API_KEY', '').strip())}")
print(f"CLAUDE_MODEL: {llm_summarize.MODEL}")
print(f"llm_summarize.is_available(): {llm_summarize.is_available()}")
print()

test_diff = """--- SHOP/pricing (prior)
+++ SHOP/pricing (new)
@@ -422,7 +422,7 @@
 Manage money with Shopify Balance
 2.28% earnings rate
-2.28% earnings rate
-2.28% earnings rate
-3.30% earnings rate
+0.00% earnings rate
+0.00% earnings rate
+0.00% earnings rate
 Flexible growth funding"""

print("Calling summarize() with a synthetic SHOP rate-cut diff...")
result = llm_summarize.summarize(
    ticker="SHOP",
    company_name="Shopify Inc.",
    source="pricing",
    url="https://www.shopify.com/pricing",
    diff_text=test_diff,
)
print()
print("Result:")
print("-" * 60)
print(result if result is not None else "(None — fallback to basic summary)")
print("-" * 60)
