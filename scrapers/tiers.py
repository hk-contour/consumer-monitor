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
BLOCKED = {
    "KLAR": "Verify SEC CIK and IR URL before building any scraper.",
    "ADYEN NA": "Verify Euronext feed (https://investors.adyen.com/financial-results) returns data; xlsx regulatory URL is wrong (points at EDGAR).",
    "ZIP AU": "Verify ASX API (https://www.asx.com.au/asx/1/company/ZIP/announcements) returns JSON; xlsx regulatory URL is wrong.",
    "8136 JP": "Verify TDnet access (https://www.release.tdnet.info/) before building.",
    "XYZ": "Confirm ticker (SQ vs XYZ). Need separate Square + Cash App scrapers.",
    "SEZL": "Need specific Sezzle Premium pricing URL — homepage is too vague.",
    "DAVE": "Need specific ExtraCash fee page URL — homepage is too vague.",
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
