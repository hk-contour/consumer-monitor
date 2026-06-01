# Consumer-monitor — build status

_Last updated: 2026-05-29. Living document; update as the project moves._

## TL;DR

A scheduled morning digest that surfaces soft signals across a consumer /
fintech / marketplace coverage universe. Scrapes pricing, T&C, management,
IR, newsroom, and SEC filings; runs each diff through Claude for
materiality classification; outputs a sorted analyst-friendly digest
(markdown + HTML, both committed to the repo).

**Repo:** https://github.com/hk-contour/consumer-monitor (private)
**Sample digest:** [HTML for print](https://raw.githack.com/hk-contour/consumer-monitor/main/monitoring_system/2026-05-29_REVIEW_SAMPLE.html)

---

## Stack

- **Python 3.12** on GitHub Actions runners — no local machine dependencies
- **Claude Haiku** via Anthropic API for per-change interpretation, cached
  by diff-hash so re-runs are free
- **xlsx** (`config/company_urls_jc.xlsx`) is the single source of truth
  for the universe and per-URL config
- **No new dependencies** beyond Python stdlib + `requests`, `beautifulsoup4`,
  `feedparser`, `openpyxl`, `python-dateutil`

---

## What works today

### Source types (live, in priority order)

| Source | Method | Status |
|---|---|---|
| **SEC EDGAR** | submissions JSON API + Form 4 / 144 XML parsing | ✅ Working — produces enriched one-liners |
| **Newsroom (RSS)** | feedparser, GUID dedup | ✅ Working for WIX |
| **Newsroom (static HTML)** | fetch + diff with noise-section strip | ✅ Working for DASH, CART, others |
| **Pricing / T&C / Mgmt / IR** | static HTML + per-URL CSS selector | ✅ Working |
| **Careers** | Greenhouse / Lever API code exists, NOT wired in | ⏳ Stub only |
| **App Store reviews** | iTunes RSS code exists, NOT wired in | ⏳ Stub only |
| **Reddit** | RSS approach designed, NOT wired in | ⏳ Deferred |

### Filters and quality controls (the signal:noise stack)

Built up in order over the project:

1. **Silent first-run baselines** — never emit "(new snapshot — no prior
   version)" entries; snapshot is written, no digest line
2. **RSS recency filter** — past 7 days only by published date
3. **EDGAR recency filter** — past **3 days** only (recently tightened
   from 7)
4. **80-char minimum-diff threshold** — ignore tiny whitespace churn
5. **Noise-section stripping** — removes geo-personalized widgets like
   "Shop local stores near you" by walking up the DOM from the heading
6. **PDF/binary URL skip** — `.pdf` / `.doc` / `.xls` URLs return clean
   fetch-failure rather than producing binary noise
7. **Bot-stub guard** — extracted text under 200 chars treated as suspect
   fetch failure so a bad response can't wipe a good baseline
8. **CSS selector per URL** (xlsx column) — narrows the extraction scope
9. **LLM materiality tagging** — every static-page change gets
   `[MATERIAL]` or `[ROUTINE]` from Claude; sorts the digest

### Digest format

- **Two top-level sections**: 🔴 Material first, ⚪ Routine second
- **Per entry**: ticker · source · materiality dot · "What it means"
  one-line LLM summary · short Detail block (added/removed) ·
  source URL · detection timestamp
- **Two output files per run**:
  - `monitoring_system/{date}_{label}.md` — for GitHub web reading
  - `monitoring_system/{date}_{label}.html` — for browser print-to-PDF
    (inline-styled diff colors, no "Background graphics" toggle needed)

---

## Coverage status

| Tier | Names | Baselined? |
|---|---|---|
| **High** (cadence: every 2h market hours when cron on) | SHOP, ETSY, TOST, BILL, DUOL, CHWY, HOOD | SHOP fully; CHWY/HOOD partially |
| **Medium** (cadence: once daily 11:06 UTC when cron on) | 21 names incl. WIX, DASH, CART | WIX, DASH, CART fully; others not yet |
| **Blocked** | ADYEN NA, ZIP AU, 8136 JP | n/a — non-US filings need custom scrapers |

**Active test set: SHOP, WIX, DASH, CART** (the 4 names we iterate on)

---

## Currently disabled (intentional)

- **Cron schedule** — turned off in `monitor.yml` while iterating on signal
  quality. Re-enable by uncommenting the two cron strings.
- **Greenhouse careers wiring** — code exists but not invoked
- **App Store reviews wiring** — code exists but not invoked
- **Reddit wiring** — recommended approach is RSS (not PRAW); not built

---

## Known issues / friction

| Issue | Status |
|---|---|
| DASH/pricing URL still 404s (merchants.doordash.com/.../merchant-pricing) | Accepted; would need different URL |
| CART investors.instacart.com IR times out from GH runner IPs (Cloudflare) | Accepted; Phase 1-tier ignored |
| Form 4/144 noise on active names (CART had 8 director RSU grants in one day) | Mitigated by 3-day EDGAR window; could go further |
| Push collisions with bot commits during manual iteration | Workflow-side; usually resolved with `git pull --rebase` |
| Snapshot clearing destroys historical change-detection capability | Lesson learned — only clear when re-baselining a small set |

---

## Roadmap (rough order)

1. **Email delivery** (SendGrid SMTP) — digest lands in inbox each
   morning instead of requiring repo click-through. ~30 min of setup.
2. **Greenhouse careers** for SHOP/DASH/CART — populate `ATS` column
   in xlsx, wire `check_careers()` into `run.py`. ~1.5 h.
3. **Expand coverage to all 28 active names** — mechanical scale-up once
   PM signs off on signal quality from the 4-name test set.
4. **Form 8-K Item-code parsing** — same enrichment we did for Form 4
   but for material-event 8-K filings. Item code → plain English (e.g.
   `Item 2.02` = earnings, `Item 5.02` = exec departure). ~30 min.
5. **Adaptive cadence** — auto-drop unchanged URLs to weekly check;
   boost frequency when an event lands. Long-term.
6. **CFPB complaints database** — high-signal for the fintech subset
   (AFRM, UPST, DAVE, SEZL, ENVA, KLAR, PYPL, HOOD).

---

## Architectural principles in force

Learned the hard way through this build. Keep enforcing them:

- **Generalize via xlsx columns, not per-company code branches.** New
  capabilities are columns the analyst can populate, not Python branches.
- **No LLM in the inner scrape loop.** LLM runs only at digest-write
  time, once per detected change, cached per-diff. Keeps cost ~$0.01/day.
- **Bias toward cheap mechanical operations.** HEAD audits, regex
  strips, URL skips beat agentic research for config cleanup.
- **Don't clear snapshots casually.** Each clear loses retrospective
  change-detection. Snapshots are precious.
- **Materiality classification at write time.** EDGAR uses form type;
  RSS defaults to material; static gets a single LLM call which serves
  both ordering and rendering.

---

## Where things live

| File | Purpose |
|---|---|
| `config/company_urls_jc.xlsx` | Universe + per-URL config (selectors, RSS feeds, ATS slugs) |
| `scrapers/config_reader.py` | Loads + parses the xlsx into Company records |
| `scrapers/static_pages.py` | HTTP fetch + BS4 extraction + noise-section stripping |
| `scrapers/edgar.py` + `edgar_enrich.py` | SEC API + Form 4/144 XML parsing |
| `scrapers/rss.py` | feedparser-based newsroom scraper |
| `scrapers/llm_summarize.py` | Anthropic API wrapper, cache, prompt v2 |
| `scrapers/tiers.py` | High/medium/blocked sets (legacy; can migrate to xlsx) |
| `run.py` | Main orchestrator |
| `digest.py` | Markdown + HTML render |
| `tools/replay_digest.py` | Replay past changelog entries through current digest writer |
| `tools/audit_urls.py` | HEAD-check every URL in the xlsx |
| `tools/add_*.py` | One-shot xlsx column additions |
| `.github/workflows/monitor.yml` | Main scrape workflow (workflow_dispatch only right now) |
| `.github/workflows/replay_digest.yml` | Generate sample digest on demand |
| `REVIEW.md` | PM-facing one-pager |
| `PHASE0_CHANGES.md` | URL audit + 54 fixes log |

---

## Quick commands

```bash
# Trigger a real scrape on the 4 test names
gh workflow run monitor.yml -f tickers=SHOP,WIX,DASH,CART

# Generate a sample digest from past changelog (since timestamp)
gh workflow run replay_digest.yml -f since=2026-05-27T20:00:00Z -f label=REVIEW_SAMPLE

# Pull latest committed digests + snapshots
git pull --ff-only

# Re-enable the cron schedule
# Edit .github/workflows/monitor.yml — uncomment the two `cron:` lines
```
