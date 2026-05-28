# Consumer Monitor — sample for review

## What this is

A scheduled morning digest that surfaces soft signals across a consumer / fintech /
marketplace coverage universe. Pulls pricing pages, T&C, management team pages, IR
sites, newsrooms, and SEC filings; runs each through a noise-stripping diff layer;
asks Claude to interpret material changes; emails (or commits to a repo) a clean
morning digest with one-line takes per change.

Goal: catch the kind of signal that doesn't make headlines but moves the thesis —
pricing changes, T&C edits, exec hires, partnership announcements, insider sale
clusters — **before** the analyst would spot them manually.

## Sample digest

A representative "busy morning" sample drawn from real data collected on 2026-05-27
to 2026-05-28 across 4 test names (SHOP, WIX, DASH, CART) plus 3 high-tier names
caught by the scheduled overnight cron (CHWY, HOOD, plus DASH/CART partial coverage):

→ [**View sample digest**](monitoring_system/2026-05-28_REVIEW_SAMPLE.md)

The sample includes 15 changes spanning every source type the system currently
captures, so you can see the full spectrum of output quality.

### Highlights worth a quick look

These were all surfaced **automatically** by the scraper and interpreted by the LLM
with no human in the loop:

- **SHOP** cut Shopify Balance earnings rates from 2.28%/3.30% to 0% across three
  plan tiers (Material — direct product/margin change)
- **CHWY** updated their product catalog disclosure from ~130k to ~190k offerings
  (~46% expansion — material operating metric update on the IR page)
- **DASH** announced Dollar Tree partnership covering 9,000+ stores (caught
  same-day from newsroom HTML)
- **CART** had 8 outside directors receive identical 6,048-share RSU grants on
  May 22 (annual director comp; routine but cleanly aggregated)
- **HOOD** renamed a fees-page section combining agentic trading with cards
  (heading rename only — flagged as low signal)
- **CART** removed a "Your Privacy Choices" footer link on Instacart Plus
  (routine, correctly classified as no-signal)

## How signals are categorized

Each digest entry includes a **What it means** line written by Claude (Haiku model)
based on the actual diff. The LLM is instructed to label each change as one of:

- **Material** — pricing/rate change, new product, exec departure, M&A activity,
  partnership, regulatory disclosure with substance
- **Routine** — section rename, layout shift, CCPA/GDPR boilerplate, periodic
  metric update without strategic implication
- **Insider activity** — Form 4/144 filings (already structured into
  "Name (Title) sold/bought N shares @ $X ($Y total) on DATE" without LLM)

We can adjust these categories or add a `[BUYWORTHY]` / `[WATCH]` etc. classification
if you'd prefer different terminology — let us know.

## What's filtered out (so you don't see it)

The system suppresses these patterns *before* they reach the digest:

- **First-run baselines** — silent the first time a URL is scraped; only real
  diffs are surfaced
- **Geographic personalization** — store widgets like "Shop local stores near you"
  with distance markers (was the dominant noise source for Instacart's pricing page)
- **Sections older than 7 days** — RSS entries and SEC filings filtered by publish
  date so the digest reflects the past week's activity, not historical inventory
- **EDGAR routine forms** — Form 3/5/S-8 et al. tagged `[ROUTINE]` so they're
  visually distinguishable from material filings (10-K, 10-Q, 8-K, DEF 14A, 13G/D)
- **Bot-stub responses** — guarded against sites returning empty HTML to scrapers
  (which would otherwise wipe our baseline and trigger spurious diffs)

## What's working today

- **4 active names** with full coverage: SHOP, WIX, DASH, CART
- **3 additional high-tier names** scraped overnight: ETSY, TOST, BILL, DUOL, CHWY, HOOD
- **Source types**: pricing, T&C, management team, IR landing, newsroom (HTML
  scrape — plus RSS for WIX), regulatory filings (SEC EDGAR API)
- **EDGAR enrichment**: Form 4 and Form 144 XML parsing → insider name, title,
  transaction type, shares, dollar value
- **LLM interpretation**: Claude Haiku, one call per static-page diff, cached
  per-diff so subsequent runs are fast
- **GitHub Actions**: every run produces a markdown digest committed to the repo

## What's coming next (in rough order)

1. **Email delivery** — currently a markdown file in the repo; next is SMTP send
   (via SendGrid) so the digest lands in your inbox each morning
2. **Greenhouse careers integration** — new VP+ hires & department clusters,
   covering SHOP/DASH/CART (plus ETSY/CHWY/HOOD/etc. once enabled)
3. **Expansion to all 28 active names** — currently 4-7 are baselined; rest
   pending after you confirm signal quality
4. **Form 8-K Item-code parsing** — same enrichment we did for Form 4, applied
   to 8-K so material event disclosures are self-explanatory in the digest

## How to give feedback

Just reply with thoughts. Specifically helpful:

1. **Anything in the sample that's noise** — false positives we should filter out
2. **Anything you'd want to see that's missing** — sources, source types, names
3. **Format preferences** — too verbose / too short, ordering, what should go at
   the top, length of "What it means" summaries
4. **Names to add or remove** from the universe
5. **Coverage gaps** — are there specific signals you actively look for that this
   wouldn't catch?

No need to be polished. Even "this is too long" or "EDGAR insider noise is useless,
collapse it into a count" is exactly what we need to hear.

---

## Implementation notes (skip unless curious)

- GitHub repo: <https://github.com/hk-contour/consumer-monitor> (private)
- Stack: Python on GitHub Actions runners. ~150 LoC scrapers + ~200 LoC orchestrator
- LLM cost: ~$0.001 per static-page diff with caching; ~$0.01/day on real cadence
- Scraping cost: ~280 HTTP requests / day on full universe, well under any rate
  limits or bot-block thresholds
