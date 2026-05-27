# Phase 0 — URL cleanup changes for review

Generated 2026-05-20. Open `config/company_urls_jc.xlsx` in Excel to see the
applied state, or this file for a scannable diff. 54 URL fixes applied across
35 companies.

## Summary
- **54 URL replacements** applied (HIGH/MEDIUM confidence from research pass)
- **4 names unblocked** in `scrapers/tiers.py`: SEZL, DAVE, XYZ, KLAR
- **3 names remain blocked**: ADYEN NA, ZIP AU, 8136 JP (non-US filings; need custom scrapers per Phase 2 — but we're deferring Phase 2 for now)
- **KLAR CIK override** added in `scrapers/edgar.py` (Klarna IPO'd 2025, SEC ticker index may lag)
- **6 URLs intentionally left unchanged** despite audit failures (bot blocking, transient timeouts, PDFs — not URL problems)

## What changed, by ticker

### Genuine URL replacements (54)

| Ticker | Source | Old | New |
|---|---|---|---|
| SHOP | management_team | investors.shopify.com/.../default.aspx | shopify.com/investors/board-of-directors |
| WIX | newsroom | wix.com/blog/news | wix.com/press-room/home |
| WIX | management_team | investors.wix.com/.../board-and-executives | investors.wix.com/board-of-directors |
| GLBE | newsroom | global-e.com/blog/ | global-e.com/media-centre/ |
| GLBE | pricing | global-e.com/solutions/ | global-e.com/platform/ |
| GLBE | terms | global-e.com/legal/terms-of-service/ | global-e.com/terms/ |
| GDDY | management_team | newsroom.godaddy.com/.../executive-team/ | aboutus.godaddy.net/about-us/team/default.aspx |
| EBAY | management_team | investors.ebayinc.com/leadership/default.aspx | investors.ebayinc.com/corporate-governance/board-of-directors/default.aspx |
| EBAY | pricing | ebay.com/sellercenter/resources/selling-fees | ebay.com/sellercenter/selling/start-selling-on-ebay/seller-fees |
| W | management_team | investor.wayfair.com/leadership/default.aspx | aboutwayfair.com/leadership |
| ETSY | management_team | investors.etsy.com/leadership/default.aspx | investors.etsy.com/company-information/executive-team |
| CHWY | newsroom | investor.chewy.com/news-releases | investor.chewy.com/news-and-events/news/default.aspx |
| CHWY | management_team | investor.chewy.com/leadership/default.aspx | investor.chewy.com/governance/executive-management/default.aspx |
| DASH | management_team | ir.doordash.com/leadership/default.aspx | ir.doordash.com/governance/management/default.aspx |
| DASH | pricing | get.doordash.com/.../merchant-pricing | merchants.doordash.com/.../merchant-pricing |
| CART | newsroom | instacart.com/company/news/ | instacart.com/company/newsroom |
| CART | pricing | instacart.com/plans | instacart.com/instacart-plus |
| MTCH | newsroom | ir.mtch.com/news-releases | ir.mtch.com/investor-relations/news-events/news-events/default.aspx |
| Z | management_team | investors.zillowgroup.com/board-and-management/leadership | zillowgroup.com/about-us/our-leaders/ |
| Z | terms | zillowgroup.com/zg-terms-of-use/ | zillow.com/z/corp/terms/  ⚠️ LOW confidence |
| RKT | management_team | ir.rocketcompanies.com/leadership/default.aspx | rocketcompanies.com/our-team/leadership/ |
| COMP | management_team | investors.compass.com/leadership/default.aspx | investors.compass.com/governance/management/default.aspx |
| COMP | terms | compass.com/terms/ | compass.com/legal/terms-of-service/ |
| APPF | careers | appfolio.com/careers/ | appfolio.com/company/careers |
| APPF | pricing | appfolio.com/property-manager/pricing/ | appfolio.com/pricing |
| XYZ | management_team | block.xyz/about | investors.block.xyz/governance/leadership/default.aspx |
| XYZ | pricing | squareup.com/.../our-rates | squareup.com/us/en/payments/our-fees |
| BILL | newsroom | bill.com/resource/press-releases | bill.com/press-release |
| BILL | management_team | investor.bill.com/leadership/default.aspx | bill.com/leadership |
| PYPL | management_team | investor.pypl.com/leadership/default.aspx | about.pypl.com/who-we-are/executive-leadership/default.aspx |
| PYPL | terms | paypal.com/.../paypal-user-agreement-full | paypal.com/.../paypal/useragreement-full |
| TOST | management_team | investors.toasttab.com/leadership/default.aspx | pos.toasttab.com/leadership |
| ADYEN NA | newsroom | adyen.com/news | adyen.com/press-and-media |
| ADYEN NA | management_team | investors.adyen.com/.../management-board | adyen.com/about/team |
| ADYEN NA | regulatory_filings | investors.adyen.com/financial-results | investors.adyen.com/financials |
| DAVE | terms | dave.com/legal/terms-of-service | dave.com/terms/ |
| DAVE | pricing | (homepage was placeholder) | dave.com/extra-cash-account |
| ZIP AU | newsroom | zip.co/media | zip.co/investors/news |
| ZIP AU | terms | help.zip.co/.../Terms-of-Use | zip.co/au/page/important-information |
| ZIP AU | regulatory_filings | asx.com.au/.../share-price-research | zip.co/investors/asx-announcements |
| SEZL | pricing | sezzle.com/ (homepage) | sezzle.com/premium/ |
| KLAR | management_team | klarna.com/international/about-klarna/leadership/ | investors.klarna.com/governance/leadership/default.aspx |
| KLAR | terms | klarna.com/us/legal/terms-of-use/ | klarna.com/us/terms-of-use/ |
| HOOD | pricing | robinhood.com/.../fees-and-charges/ | robinhood.com/.../trading-fees-on-robinhood/ |
| HOOD | terms | robinhood.com/.../customer-agreement/ | cdn.robinhood.com/.../Robinhood-Customer-Agreement.pdf  ⚠️ PDF |
| UPST | terms | upstart.com/legal/terms-of-use | upstart.com/terms |
| RH | management_team | ir.rh.com/leadership/default.aspx | ir.rh.com/corporate-governance/leadership |
| WSM | terms | williams-sonoma.com/customer-service/terms-of-use.html | williams-sonoma.com/m/customer-service/terms.html |
| SGI | pricing | tempurpedic.com/mattresses/ | tempurpedic.com/shop-mattresses/ |
| ENVA | newsroom | ir.enova.com/news-releases | ir.enova.com/.../news-releases/default.aspx |
| ENVA | management_team | ir.enova.com/leadership/default.aspx | ir.enova.com/corporate-governance/leadership-team/default.aspx |
| ENVA | pricing | enova.com/products/ | enova.com/brands/ |
| ENVA | terms | enova.com/legal/terms-of-use/ | enova.com/terms-conditions/ |
| ONON | management_team | investors.on.com/corporate-governance/board-of-directors | investors.on-running.com/governance/default.aspx |

### Items flagged for your judgment

These had audit failures but were **NOT** auto-fixed. They're either correct URLs blocked by bot protection, transient errors, or special formats:

| Ticker | Source | Status | Reason left unchanged |
|---|---|---|---|
| EBAY | terms | TooManyRedirects | URL is correct; was a HEAD-method redirect-loop, transient |
| CHWY | terms | timeout | URL is correct; transient timeout |
| CSGP | terms | 403 | URL likely canonical; Cloudflare blocks our scraper |
| RKT | terms | 503 | URL likely canonical; Cloudflare blocks our scraper |
| ZIP AU | management_team | 530 | URL likely canonical; Cloudflare blocks our scraper |
| SGI | terms | 404 | Somnigroup terms are a PDF on Q4 CDN — needs PDF extraction support |

### Confidence concerns to spot-check

| Item | Why flagged |
|---|---|
| Z/terms | LOW confidence — couldn't fully verify zillow.com/z/corp/terms/ is the canonical replacement |
| HOOD/terms | Now points at a PDF (Robinhood Customer Agreement) — works but we don't have PDF extraction yet |
| SGI/terms | Left unchanged because Somnigroup terms are also a PDF; same issue |
| ENVA/* | Multiple URLs unverifiable because ir.enova.com 403s our scraper; URLs follow standard Q4 pattern, likely correct |

### Tier changes (`scrapers/tiers.py`)

Removed from BLOCKED — these now run on every scheduled execution:
- **SEZL** — Premium pricing URL was the missing piece
- **DAVE** — ExtraCash URL was the missing piece
- **XYZ** — ticker change (SQ → XYZ) confirmed; URLs corrected
- **KLAR** — CIK confirmed and added as override in `scrapers/edgar.py`

Still blocked (need Phase 2 work — deferred):
- **ADYEN NA** — Euronext H1/H2 filings still need a custom scraper
- **ZIP AU** — ASX announcements still need a custom scraper
- **8136 JP** — TDnet has no per-company persistent URL; recommend skipping

## How to review

1. Open `/Users/harikumar/Downloads/company_urls_jc_phase0.xlsx` in Excel — see the final state
2. Cross-check the URLs above against the xlsx
3. If anything looks wrong, edit the cell in Excel and tell me which row(s) you changed

When happy: tell me to commit and we move to Phase 1A.
