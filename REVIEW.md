# Consumer Monitor — sample for review

## What this is

A scheduled morning digest that surfaces soft signals across a consumer / fintech /
marketplace coverage universe. Pulls pricing pages, T&C, management team pages, IR
sites, newsrooms, and SEC filings; runs each through a noise-stripping diff layer;
asks Claude to interpret material changes; emails (or commits to a repo) a clean
morning digest with one-line takes per change.

Goal: catch the kind of signal that doesn't make headlines but moves the thesis —
pricing changes, T&C edits, exec hires, partnership announcements, regulatory
filings — **before** the analyst would spot them manually.

## Sample digest

A representative sample drawn from real data collected on 2026-05-27 to 2026-05-28:

→ [**View sample digest**](monitoring_system/2026-05-28_REVIEW_SAMPLE.md)

5 changes total, split into two sections (Material first, Routine second). The
sample shows exactly what a morning email would look like in plain text or HTML.

### What's in the sample

**Material (3) — read these:**
- **SHOP** cut Shopify Balance earnings rates from 2.28%/3.30% to 0% across three
  plan tiers (margin-positive; potential churn risk on Plus)
- **CHWY** expanded product catalog disclosure from ~130k to ~190k SKUs on IR page
  (~46% growth — quantitative operating metric update)
- **DASH** announced Dollar Tree partnership covering 9,000+ stores, plus FIFA
  World Cup 2026 sponsorship with $5M DashPass credits

**Routine (2) — skim or skip:**
- **CART** removed a "Your Privacy Choices" footer link on Instacart Plus
- **HOOD** section rename combining agentic trading with cards (heading-only)

Every entry was surfaced **automatically** by the scraper and interpreted by
Claude Haiku with no human in the loop. The LLM also tagged each as `[MATERIAL]` /
`[ROUTINE]` so the digest can be sorted by importance.

## How signals are categorized

The LLM is instructed to prefix every static-page interpretation with one of:

| Tag | Triggers when the change involves |
|---|---|
| `[MATERIAL]` | Pricing/rate/fee change; new product or plan; exec hire/departure; partnership, M&A, regulatory action; quantitative metric update (catalog size, store count) |
| `[ROUTINE]` | Section rename or layout shift; date-stamp refresh; CCPA/GDPR/cookie boilerplate; typo/formatting fix; PDF re-encoding; pure rotation of news posts |

EDGAR filings are classified by form type without LLM (10-K / 10-Q / 8-K / 13G/D
= Material; Form 4 / 144 / 3 / 5 / S-8 = Routine). RSS press releases default to
Material since they're publisher-gated content.

## What's filtered out (so you don't see it)

The system suppresses these patterns *before* they reach the digest:

- **First-run baselines** — silent the first time a URL is scraped; only real
  diffs ever surface
- **Geographic personalization** — store widgets like "Shop local stores near you"
  with distance markers (was the dominant noise source for Instacart's pricing)
- **EDGAR window** — filings older than **3 days** are excluded; the cluster of
  director RSU grants and insider sales from May 22 (6 days ago) no longer
  appears in this sample
- **RSS / static recency** — news items older than 7 days are filtered out
- **Bot-stub responses** — guarded against sites returning empty HTML to scrapers
  (which would otherwise wipe baselines and trigger spurious diffs)
- **Binary files** (PDF/DOC/XLS/etc.) — skipped entirely; their byte-level
  re-encoding shows up as gibberish diffs that are noise, not signal

## What's working today

- **4 active names** with full coverage: SHOP, WIX, DASH, CART
- **3 additional high-tier names** previously scraped by overnight cron and
  baselined: CHWY, HOOD, plus partial coverage on ETSY/TOST/BILL/DUOL
- **Source types**: pricing, T&C, management team, IR landing, newsroom (HTML
  scrape — plus RSS for WIX), regulatory filings (SEC EDGAR JSON API)
- **EDGAR enrichment**: Form 4 and Form 144 XML parsing → insider name, title,
  transaction type, shares, dollar value (all inline in the digest)
- **LLM interpretation**: Claude Haiku, one call per static-page diff,
  cached per-diff so repeat runs are free
- **Material / Routine split**: top-of-digest count + two separate sections
  for fast triage

## What's coming next (in rough order)

1. **Email delivery** — currently a markdown file in the repo; next is SMTP
   send (via SendGrid) so the digest lands in your inbox each morning
2. **Greenhouse careers integration** — new VP+ hires & department clusters,
   covering SHOP/DASH/CART/CHWY/ETSY/HOOD/etc.
3. **Expansion to all 28 active names** — currently 4-7 baselined; rest
   pending after you confirm signal quality
4. **Form 8-K Item-code parsing** — same enrichment we did for Form 4, applied
   to 8-K so material event disclosures are self-explanatory in the digest

## How to give feedback

Just reply with thoughts. Specifically helpful:

1. **Anything in the sample that's noise** — false positives we should filter
   out. (The CART CCPA-link removal and HOOD section rename are both in the
   Routine section by design, but tell us if you'd prefer them suppressed entirely.)
2. **Anything you'd want to see that's missing** — sources, source types, names
3. **Format preferences** — too verbose / too short; ordering; what should go
   at the top; length of "What it means" summaries
4. **Names to add or remove** from the universe
5. **Coverage gaps** — are there specific signals you actively look for that
   this wouldn't catch?

No need to be polished. Even "this is too long" or "I don't care about
director RSU grants" is exactly what we need to hear.

---

## Implementation notes (skip unless curious)

- GitHub repo: <https://github.com/hk-contour/consumer-monitor> (private)
- Stack: Python on GitHub Actions runners. ~200 LoC scrapers + ~250 LoC orchestrator
- LLM cost: ~$0.001 per static-page diff with caching; ~$0.01/day at full cadence
- Scraping cost: ~280 HTTP requests / day on the full universe, well under any
  rate-limit or bot-block thresholds
