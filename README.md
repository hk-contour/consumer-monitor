# consumer-monitor

Scheduled morning monitoring for a 35-company consumer / fintech / marketplace coverage
universe. Tracks soft signals across pricing, T&C, management, careers, regulatory
filings, and community forums. Produces a daily markdown digest and appends flagged
changes to the Signal Feedback Log in the master xlsx.

## Where it runs

GitHub Actions, on schedule. See `.github/workflows/monitor.yml`.

## Source of truth

`config/company_urls_jc.xlsx` — URL Registry tab is the canonical config. Edit the
xlsx, commit, and the next run picks up the change.

## Layout

```
config/                  master xlsx (URL Registry, Signal Feedback Log, How To Use)
scrapers/                one module per source type
snapshots/               git-tracked extracted text; git history = changelog
monitoring_system/       daily digest markdown output
changelog.jsonl          append-only diff log
run.py                   orchestrator
.github/workflows/       schedule + secrets
```

## Snapshots and diffs

Each run extracts clean text (nav/header/footer/scripts stripped) from each tracked
URL, hashes it, and compares against the prior snapshot. If different, runs
`difflib.unified_diff`, logs to `changelog.jsonl`, and commits the new snapshot. Git
itself is the diff archive.

## Priority tiers

Defined in `scrapers/tiers.py` (sourced from the build briefing — pending migration
into the xlsx as a real column).

- **High** — every 2 hours, 6am–6pm ET, weekdays. 7 names.
- **Medium** — once daily 6:06am ET, weekdays. 24 names.
- **Fix First** — skipped until data issues resolved. 6 names.

## Secrets (GitHub Actions repository secrets)

- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT`

## Status

Scaffolding stage. Config reader and snapshot store are working; individual scrapers
are stubbed. See the build briefing for the full plan.
