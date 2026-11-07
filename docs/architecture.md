# Level 5 pipeline architecture

The project uses one shared scraper/matcher core and one common runner with four operating modes.

```text
External sources
      |
      v
scrapers + models + validation
      |
      v
   app/runner.py
      |
  +---+---------+------------+-------------+
  |             |            |             |
  v             v            v             v
 PR check     health      production      debug
  |             |            |             |
 tests       stateful       SQLite      JSON/error
 registry    monitoring     + matcher    artifacts
                |
             Telegram
          on transitions only
```

## Modes

- `pr`: deterministic pre-merge validation; unit tests plus source registry validation; no external scrape.
- `health`: checks sources without writing production data. State is persisted in `data/health_state.json`. Telegram is sent only when a source changes into a problem state or recovers.
- `production`: restores the previous production SQLite database, scrapes each source independently, preserves prior data for sources that fail, validates Czech athletics event counts, and atomically replaces the iDNES programme after a complete, nonempty scrape.
- `debug`: runs one selected source and uploads parsed JSON plus an exception traceback when present.

## Source registry

`app/registry.py` is the single place that maps source names to scraper implementations and source-specific policy. The active sources are iDNES, Atletika.cz, and official Czech athletics YouTube streams discovered via Atletika.cz. A lack of scheduled YouTube streams is valid.

## iDNES and reports

The scraper reads channel grids over HTTP and resolves ambiguous programme
details. Rules in `config/watched_sports.yaml` match the competition and, where
required, the participants. Reports use iDNES broadcast times. Oneplay
multigame blocks carry fixture-specific MD routes when iDNES supplies them.
The weekly report also includes the Czech championships from Atletika.cz,
which are paired with official YouTube streams by event name and date.
Older organizer rows in restored databases are ignored by report queries.

## GitHub Actions

- `pr-check.yml`: runs for pull requests to `main`.
- `health.yml`: manual health monitoring.
- `production.yml`: manual production run.
- `debug.yml`: manual diagnosis of exactly one source.
- `_pipeline.yml`: reusable implementation shared by all workflows.

`concurrency` prevents overlapping runs for the same mode/source. Production deliberately does not cancel an in-flight run when another production run starts.

## Persistence

GitHub Actions restores and saves:

- `data/sports_events.db` for production continuity,
- `data/validation_state.json` for event-count anomaly detection,
- `data/health_state.json` for DOWN/RECOVERED transition detection.

The production database is also uploaded as an artifact after every production run.

## Telegram secrets

Configure these GitHub repository secrets before expecting notifications:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Health still runs safely without them; the workflow logs that notification delivery was skipped.

## Failure isolation

A scraper exception does not stop the remaining sources. In production the previous SQLite data stays available for the failed source because the database is restored before the run and failed sources are not overwritten.

A production workflow still exits as failed when a source is DOWN so GitHub clearly reports degraded production, while the other sources have already been processed and the database artifact is still uploaded.
