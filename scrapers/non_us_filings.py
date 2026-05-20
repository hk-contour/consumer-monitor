"""Non-US filing system scrapers — one per exchange.

All three are currently BLOCKED (see scrapers/tiers.BLOCKED). Build out once
endpoint access is verified.

  ADYEN NA -> Euronext Amsterdam IR page:
              https://investors.adyen.com/financial-results
              H1 and H2 only, no quarterly cadence.

  ZIP AU   -> ASX announcements JSON API:
              https://www.asx.com.au/asx/1/company/ZIP/announcements

  8136 JP  -> TDnet (Tokyo Stock Exchange disclosure):
              https://www.release.tdnet.info/
              Japanese filing system; structured access tbd.

Note: WIX, GLBE, ONON are US-listed but file 20-F (annual only). Use the
edgar scraper, but adjust cadence — don't expect quarterly filings.
"""

from __future__ import annotations


def fetch_adyen() -> list[dict]:
    raise NotImplementedError("Adyen Euronext scraper — blocked until URL verified.")


def fetch_zip_au() -> list[dict]:
    raise NotImplementedError("ASX ZIP scraper — blocked until JSON API verified.")


def fetch_8136_jp() -> list[dict]:
    raise NotImplementedError("TDnet 8136 scraper — blocked until access verified.")
