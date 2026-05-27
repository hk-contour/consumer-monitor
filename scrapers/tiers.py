"""Priority tier mapping, sourced from the build briefing.

Tickers match the xlsx exactly (e.g. "ADYEN NA", "ZIP AU", "8136 JP").

HIGH / MEDIUM are cadence groups. BLOCKED is orthogonal — names with
unresolved data issues that should be skipped even if they otherwise sit in
HIGH or MEDIUM. `tier_for()` returns "blocked" first; the orchestrator skips.

Will migrate into the xlsx as a real `Priority Tier` column once the analyst
adds it. Until then, this dict is authoritative.
"""

HIGH = {"SHOP", "ETSY", "TOST", "BILL", "DUOL", "CHWY", "HOOD"}

MEDIUM = {
    "PYPL", "APPF", "RKT", "DASH", "MTCH", "CART", "AFRM", "Z", "GDDY",
    "EBAY", "UPST", "XYZ", "CSGP", "WIX", "GLBE", "W", "COMP", "RH",
    "WSM", "SGI", "ENVA", "ONON", "SEZL", "DAVE",
}

# Names with unresolved data issues — skip every run until fixed.
# Post-Phase-0 audit (2026-05-20): SEZL, DAVE, XYZ, KLAR resolved and unblocked.
# ADYEN NA, ZIP AU, 8136 JP remain blocked pending custom non-US filing scrapers.
BLOCKED = {
    "ADYEN NA": "Filings URL fixed to investors.adyen.com/financials. Still needs custom Euronext H1/H2 scraper (non-quarterly cadence).",
    "ZIP AU":   "Filings URL fixed to zip.co/investors/asx-announcements. Still needs custom ASX announcements scraper.",
    "8136 JP":  "TDnet has no per-company persistent URL (~31-day retention). Long-term archive needs third-party (magicalir.net) integration.",
}


def tier_for(ticker: str) -> str:
    """Return "high" | "medium" | "blocked" | "unknown"."""
    t = ticker.strip().upper()
    if t in BLOCKED:
        return "blocked"
    if t in HIGH:
        return "high"
    if t in MEDIUM:
        return "medium"
    return "unknown"


def blocker_reason(ticker: str) -> str | None:
    return BLOCKED.get(ticker.strip().upper())
