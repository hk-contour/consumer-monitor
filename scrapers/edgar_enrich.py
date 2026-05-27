"""EDGAR filing enrichment — parse Form 4 / Form 144 XML for transaction details.

Turns "New 4 filed 2026-05-22 (accession 0001833552-26-000008)" into
"Tony Xu (CEO) sold 12,500 shares @ $234.50 ($2.93M) on 2026-05-20".

Form types covered:
  - Form 4: insider trade reports (P=purchase, S=sale, A=grant, M=exercise, F=tax withhold)
  - Form 144: notice of proposed insider sale
  - All other forms: fall back to FORM_DESCRIPTIONS lookup

XML is cached on disk by accession number — filings are immutable so the cache
never goes stale. Subsequent runs re-parse from cache, not over the network.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

UA = "consumer-monitor/0.1 (Contour Asset Management; hari.kumar@contourasset.com)"
CACHE_DIR = Path(__file__).resolve().parent.parent / "snapshots" / "_edgar_cache" / "xml"


# Form code -> (plain English description, materiality tag)
FORM_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "10-K":     ("Annual report", "MATERIAL"),
    "10-Q":     ("Quarterly report", "MATERIAL"),
    "8-K":      ("Material event disclosure", "MATERIAL"),
    "DEF 14A":  ("Proxy statement (annual meeting / governance vote)", "MATERIAL"),
    "S-1":      ("Initial registration / IPO", "MATERIAL"),
    "S-3":      ("Secondary offering registration", "MATERIAL"),
    "S-4":      ("M&A registration", "MATERIAL"),
    "SC 13G":   ("Passive 5%+ owner disclosure", "MATERIAL"),
    "SC 13D":   ("Active 5%+ owner — possible activist", "MATERIAL"),
    "SCHEDULE 13G/A": ("Update to 5%+ passive owner disclosure", "MATERIAL"),
    "SCHEDULE 13D/A": ("Update to 5%+ active owner disclosure", "MATERIAL"),
    "4":        ("Insider trade", "ROUTINE"),
    "144":      ("Notice of proposed insider sale", "ROUTINE"),
    "3":        ("New insider — initial ownership statement", "ROUTINE"),
    "5":        ("Annual insider ownership statement", "ROUTINE"),
    "S-8":      ("Employee stock plan registration", "ROUTINE"),
    "S-8 POS":  ("Employee stock plan amendment", "ROUTINE"),
}

# Form 4 transaction codes (SEC schedule)
TRANSACTION_CODES = {
    "P": "purchase (open market)",
    "S": "sale (open market)",
    "A": "grant/award",
    "D": "disposition",
    "M": "option exercise",
    "F": "tax withholding on vest",
    "G": "gift",
    "J": "other",
    "V": "voluntary report",
    "X": "expiration",
}


def describe_form(form_code: str) -> tuple[str, str]:
    """Return (description, materiality) for a form code; sensible default if unknown."""
    if form_code in FORM_DESCRIPTIONS:
        return FORM_DESCRIPTIONS[form_code]
    # Schedule 13G/D variants
    if form_code.startswith("SC 13"):
        return ("5%+ ownership disclosure", "MATERIAL")
    return (f"Form {form_code}", "UNKNOWN")


def _raw_xml_url(filing_url: str) -> str:
    """Strip XSL viewer segment from filing URL to get raw XML.

    SEC serves XML files at two URLs: the one we get from the submissions API
    has an `xsl{TAG}/` segment that wraps the XML in an HTML viewer. The raw
    XML is at the same URL minus that segment.
    """
    return re.sub(r"/xsl[^/]+/", "/", filing_url)


def _fetch_xml(url: str, accession: str | None = None) -> str | None:
    """Fetch raw XML, cached by accession (filings are immutable)."""
    if accession:
        cache_file = CACHE_DIR / f"{accession.replace('-', '')}.xml"
        if cache_file.exists():
            return cache_file.read_text(encoding="utf-8")
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    text = r.text
    if accession:
        cache_file = CACHE_DIR / f"{accession.replace('-', '')}.xml"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(text, encoding="utf-8")
    return text


def _strip_namespaces(root: ET.Element) -> ET.Element:
    """Strip XML namespaces from all element tags so XPath lookups work uniformly.

    SEC's ownership XMLs (Form 144 uses default namespace, Form 4 doesn't).
    Easier to normalize than to thread namespace maps through every findtext.
    """
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]
    return root


def _humanize_name(name: str) -> str:
    """LASTNAME FIRSTNAME → Firstname Lastname. Leave already-mixed-case names alone."""
    if not name:
        return ""
    name = name.strip()
    if not name.isupper():
        return name
    parts = name.split()
    if len(parts) < 2:
        return name.title()
    # SEC convention: LAST FIRST [MIDDLE]
    last = parts[0].title()
    rest = " ".join(p.title() for p in parts[1:])
    return f"{rest} {last}"


def _fmt_value(amount: float) -> str:
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.2f}M"
    if amount >= 1_000:
        return f"${amount / 1_000:.1f}K"
    return f"${amount:.0f}"


def _fmt_shares(n: float) -> str:
    return f"{n:,.0f}"


def summarize_form_4(filing_url: str, accession: str | None = None) -> str | None:
    """Fetch + parse Form 4 XML. Returns one-line summary or None on failure."""
    xml = _fetch_xml(_raw_xml_url(filing_url), accession)
    if not xml:
        return None
    try:
        root = _strip_namespaces(ET.fromstring(xml))
    except ET.ParseError:
        return None

    # Owner
    owner_name = (root.findtext(".//reportingOwner/reportingOwnerId/rptOwnerName") or "").strip()
    owner_name = _humanize_name(owner_name)

    # Title (Director / Officer + officer title / 10%+ owner)
    rel = root.find(".//reportingOwner/reportingOwnerRelationship")
    titles: list[str] = []
    if rel is not None:
        if (rel.findtext("isOfficer") or "0").strip() in ("1", "true"):
            officer_title = (rel.findtext("officerTitle") or "").strip()
            titles.append(officer_title or "Officer")
        if (rel.findtext("isDirector") or "0").strip() in ("1", "true"):
            titles.append("Director")
        if (rel.findtext("isTenPercentOwner") or "0").strip() in ("1", "true"):
            titles.append("10%+ owner")

    title_str = titles[0] if titles else "Insider"
    owner_str = f"{owner_name} ({title_str})" if owner_name else title_str

    # Transactions — aggregate by code so multi-row Form 4s compress cleanly
    sales: list[tuple[float, float, str]] = []     # (shares, price, date)
    purchases: list[tuple[float, float, str]] = []
    grants: list[tuple[float, str]] = []           # (shares, date)
    tax_with: list[tuple[float, str]] = []
    other: list[tuple[str, float, str]] = []       # (code, shares, date)

    for txn in root.findall(".//nonDerivativeTransaction"):
        code = (txn.findtext(".//transactionCode") or "").strip()
        date = (txn.findtext(".//transactionDate/value") or "").strip()
        try:
            shares = float(txn.findtext(".//transactionShares/value") or 0)
            price = float(txn.findtext(".//transactionPricePerShare/value") or 0)
        except ValueError:
            continue
        if code == "S":
            sales.append((shares, price, date))
        elif code == "P":
            purchases.append((shares, price, date))
        elif code == "A":
            grants.append((shares, date))
        elif code == "F":
            tax_with.append((shares, date))
        else:
            other.append((code, shares, date))

    parts: list[str] = []
    if sales:
        total_shares = sum(s for s, _, _ in sales)
        total_value = sum(s * p for s, p, _ in sales)
        avg_price = total_value / total_shares if total_shares else 0
        date = sales[0][2]
        parts.append(f"sold {_fmt_shares(total_shares)} shares @ ${avg_price:.2f} "
                     f"({_fmt_value(total_value)}) on {date}")
    if purchases:
        total_shares = sum(s for s, _, _ in purchases)
        total_value = sum(s * p for s, p, _ in purchases)
        avg_price = total_value / total_shares if total_shares else 0
        date = purchases[0][2]
        parts.append(f"BOUGHT {_fmt_shares(total_shares)} shares @ ${avg_price:.2f} "
                     f"({_fmt_value(total_value)}) on {date}")
    if grants and not (sales or purchases):
        total_shares = sum(s for s, _ in grants)
        date = grants[0][1]
        parts.append(f"RSU/grant of {_fmt_shares(total_shares)} shares on {date}")
    if tax_with and not (sales or purchases or grants):
        total_shares = sum(s for s, _ in tax_with)
        date = tax_with[0][1]
        parts.append(f"{_fmt_shares(total_shares)} shares withheld for taxes (vest event) on {date}")
    if not parts and other:
        code, shares, date = other[0]
        parts.append(f"{TRANSACTION_CODES.get(code, code)}: {_fmt_shares(shares)} shares on {date}")

    if not parts:
        return None
    return f"{owner_str} {'; '.join(parts)}"


def summarize_form_144(filing_url: str, accession: str | None = None) -> str | None:
    """Fetch + parse Form 144 (notice of intent to sell)."""
    xml = _fetch_xml(_raw_xml_url(filing_url), accession)
    if not xml:
        return None
    try:
        root = _strip_namespaces(ET.fromstring(xml))
    except ET.ParseError:
        return None

    # Form 144 actual field paths (verified against DASH filings):
    seller = (root.findtext(".//nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold")
              or "").strip()
    seller = _humanize_name(seller)

    relationship = (root.findtext(".//relationshipToIssuer") or "").strip()

    try:
        shares = float(root.findtext(".//securitiesInformation/noOfUnitsSold") or 0)
        value = float(root.findtext(".//securitiesInformation/aggregateMarketValue") or 0)
    except (ValueError, TypeError):
        shares = value = 0

    approx_date = (root.findtext(".//securitiesInformation/approxSaleDate") or "").strip()

    if not (seller or shares):
        return None

    owner_str = f"{seller} ({relationship})" if seller and relationship else (seller or "Insider")
    parts = [f"{owner_str} plans to sell {_fmt_shares(shares)} shares"]
    if value:
        parts.append(f"(~{_fmt_value(value)})")
    if approx_date:
        parts.append(f"on/after {approx_date}")
    return " ".join(parts) if parts else None


def summarize(form: str, filing_url: str, accession: str | None = None) -> tuple[str, str]:
    """Return (rich_summary, materiality).

    Falls back to FORM_DESCRIPTIONS lookup when form-specific parsing isn't
    implemented or fails.
    """
    desc, materiality = describe_form(form)

    rich: str | None = None
    if form == "4":
        rich = summarize_form_4(filing_url, accession)
    elif form == "144":
        rich = summarize_form_144(filing_url, accession)

    if rich:
        return (f"{desc} — {rich}", materiality)
    return (desc, materiality)
