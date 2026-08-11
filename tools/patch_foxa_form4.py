"""One-off: re-enrich the 4 FOXA Form 4 entries in today's changelog + digest.

These filings were scraped before edgar_enrich learned to read the derivative
table, so they were recorded as a bare "[ROUTINE] Insider trade". The parser
is now fixed and the XML is cached, so we recompute the rich summary and patch
it into the changelog line, the Markdown digest, and the HTML digest in place.

The EDGAR scraper won't re-emit these filings (their accession is already the
stored high-water mark), so a fresh workflow run can't regenerate them — an
in-place patch is the only way to correct today's deliverable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers import edgar_enrich  # noqa: E402

DIGEST_DATE = "2026-08-11"

# accession (no dashes) -> filing URL from the changelog
FOXA = {
    "000162828026055391": "https://www.sec.gov/Archives/edgar/data/1754301/000162828026055391/xslF345X06/wk-form4_1786398011.xml",
    "000162828026055392": "https://www.sec.gov/Archives/edgar/data/1754301/000162828026055392/xslF345X06/wk-form4_1786398055.xml",
    "000162828026055396": "https://www.sec.gov/Archives/edgar/data/1754301/000162828026055396/xslF345X06/wk-form4_1786398195.xml",
    "000162828026055398": "https://www.sec.gov/Archives/edgar/data/1754301/000162828026055398/xslF345X06/wk-form4_1786398279.xml",
}


def main() -> int:
    # url -> new rich summary (e.g. "Insider trade — Lachlan K Murdoch (...) granted ...")
    rich: dict[str, str] = {}
    for acc, url in FOXA.items():
        summary, _materiality = edgar_enrich.summarize("4", url, acc)
        if summary == "Insider trade":
            print(f"  !! {acc} still bare — parser did not enrich", file=sys.stderr)
            return 1
        rich[url] = summary
        print(f"  {acc} -> {summary}")

    # 1) changelog.jsonl — rewrite the diff field for matching FOXA edgar:4 rows
    cl = ROOT / "changelog.jsonl"
    out_lines: list[str] = []
    patched_cl = 0
    for line in cl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            out_lines.append(line)
            continue
        obj = json.loads(line)
        if (obj.get("ticker") == "FOXA" and obj.get("source") == "edgar:4"
                and obj.get("url") in rich):
            obj["diff"] = f"[ROUTINE] {rich[obj['url']]}"
            out_lines.append(json.dumps(obj, ensure_ascii=False))
            patched_cl += 1
        else:
            out_lines.append(line)
    cl.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"changelog: patched {patched_cl} rows")

    # 2) Markdown + 3) HTML digests — replace the "Insider trade" label that
    #    precedes each FOXA filing URL with the full enriched summary.
    for ext, (needle_tmpl, repl_tmpl) in {
        "md": ("**FOXA — SEC filing (4):** Insider trade [↗]({url})",
               "**FOXA — SEC filing (4):** {sum} [↗]({url})"),
        "html": ('<b>FOXA — SEC filing (4):</b> Insider trade <a href="{url}">',
                 '<b>FOXA — SEC filing (4):</b> {sum} <a href="{url}">'),
    }.items():
        matches = sorted((ROOT / "monitoring_system").glob(f"{DIGEST_DATE}_*.{ext}"))
        if not matches:
            print(f"  !! no {ext} digest for {DIGEST_DATE}", file=sys.stderr)
            return 1
        path = matches[-1]
        text = path.read_text(encoding="utf-8")
        patched = 0
        for url, summary in rich.items():
            needle = needle_tmpl.format(url=url)
            repl = repl_tmpl.format(sum=summary, url=url)
            if needle in text:
                text = text.replace(needle, repl)
                patched += 1
        path.write_text(text, encoding="utf-8")
        print(f"{ext}: patched {patched} lines")

    return 0


if __name__ == "__main__":
    sys.exit(main())
