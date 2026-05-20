"""App Store release notes via iTunes Search API.

Endpoint: https://itunes.apple.com/lookup?bundleId={bundle_id}&country=us

Returns version history with release notes and dates. Bundle IDs to populate
once confirmed per app (Pre-Build Step):
  DUOL -> com.duolingo.DuolingoMobile
  CHWY -> com.chewy.mobile
  DASH -> com.dd.doordash
  CART -> com.instacart.client
  HOOD -> com.robinhood.release.Robinhood
  MTCH -> separate apps: Tinder (com.cardify.tinder) + Hinge (co.match.hinge)
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

from .static_pages import USER_AGENT

LOOKUP_URL = "https://itunes.apple.com/lookup"

BUNDLE_IDS: dict[str, list[str]] = {
    # ticker -> [bundle_ids]. Multiple if a co. has multiple flagship apps.
    # "DUOL": ["com.duolingo.DuolingoMobile"],
    # "CHWY": ["com.chewy.mobile"],
    # "MTCH": ["com.cardify.tinder", "co.match.hinge"],
}


@dataclass
class AppVersion:
    bundle_id: str
    app_name: str
    version: str
    release_date: str
    release_notes: str
    track_view_url: str


PRICING_KEYWORDS = ("price", "pricing", "subscription", "premium", "plus",
                    "upgrade", "membership", "fee", "paywall")


def lookup_bundle(bundle_id: str) -> AppVersion | None:
    r = requests.get(LOOKUP_URL, params={"bundleId": bundle_id, "country": "us"},
                     headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results:
        return None
    app = results[0]
    return AppVersion(
        bundle_id=bundle_id,
        app_name=app.get("trackName", ""),
        version=app.get("version", ""),
        release_date=app.get("currentVersionReleaseDate", ""),
        release_notes=app.get("releaseNotes", ""),
        track_view_url=app.get("trackViewUrl", ""),
    )


def latest_versions_for(ticker: str) -> list[AppVersion]:
    bundles = BUNDLE_IDS.get(ticker.strip().upper(), [])
    out: list[AppVersion] = []
    for bid in bundles:
        v = lookup_bundle(bid)
        if v:
            out.append(v)
    return out


def has_pricing_keyword(notes: str) -> bool:
    n = notes.lower()
    return any(k in n for k in PRICING_KEYWORDS)
