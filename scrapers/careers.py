"""Careers / jobs scrapers.

Three backends:
  1. Greenhouse:  https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
  2. Lever:       https://api.lever.co/v0/postings/{slug}
  3. Workday:     no public API — fall back to static_pages.fetch_and_extract.

ATS slugs must be discovered per company (Pre-Build Step 2 in the briefing).
Populate ATS_REGISTRY below as you confirm each one.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

from .static_pages import USER_AGENT

GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
LEVER_URL = "https://api.lever.co/v0/postings/{slug}"

# ticker -> (ats_type, slug). Slugs verified by hitting the Greenhouse Job
# Board API and confirming 200 + non-empty jobs array. Each line below was
# checked 2026-06-01 and returned the indicated job count.
ATS_REGISTRY: dict[str, tuple[str, str]] = {
    "DUOL": ("greenhouse", "duolingo"),   # 60 jobs
    "HOOD": ("greenhouse", "robinhood"),  # 130 jobs
    "CART": ("greenhouse", "instacart"),  # 134 jobs
    "AFRM": ("greenhouse", "affirm"),     # 163 jobs
    "TOST": ("greenhouse", "toast"),      # 333 jobs
    "UPST": ("greenhouse", "upstart"),    # 80 jobs
    # Briefing claimed SHOP/ETSY/DASH/CHWY use Greenhouse but the obvious
    # slugs 404 — they likely migrated or use different slugs.
    # For those names careers stays on HTML scrape (which works for SHOP).
}


@dataclass
class JobPosting:
    title: str
    department: str
    location: str
    url: str
    job_id: str


def fetch_greenhouse(slug: str) -> list[JobPosting]:
    r = requests.get(GREENHOUSE_URL.format(slug=slug),
                     headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    out: list[JobPosting] = []
    for job in r.json().get("jobs", []):
        depts = ", ".join(d["name"] for d in job.get("departments", []))
        out.append(JobPosting(
            title=job.get("title", ""),
            department=depts,
            location=(job.get("location") or {}).get("name", ""),
            url=job.get("absolute_url", ""),
            job_id=str(job.get("id", "")),
        ))
    return out


def fetch_lever(slug: str) -> list[JobPosting]:
    r = requests.get(LEVER_URL.format(slug=slug),
                     headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    out: list[JobPosting] = []
    for job in r.json():
        out.append(JobPosting(
            title=job.get("text", ""),
            department=(job.get("categories") or {}).get("team", ""),
            location=(job.get("categories") or {}).get("location", ""),
            url=job.get("hostedUrl", ""),
            job_id=job.get("id", ""),
        ))
    return out


def fetch_jobs(ticker: str) -> list[JobPosting]:
    entry = ATS_REGISTRY.get(ticker.strip().upper())
    if not entry:
        return []
    ats, slug = entry
    if ats == "greenhouse":
        return fetch_greenhouse(slug)
    if ats == "lever":
        return fetch_lever(slug)
    # workday or unknown -> caller falls back to static_pages
    return []


def is_senior(title: str) -> bool:
    """Flag VP+ titles. The briefing's signal threshold."""
    t = title.lower()
    keywords = ("vp ", "vice president", "head of", "chief ", "svp", "evp",
                "director of", "general manager")
    return any(k in t for k in keywords)
