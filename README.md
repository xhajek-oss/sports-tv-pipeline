# sports-tv-pipeline

Resilient Level 5 sports and TV data pipeline.

The project uses one shared Python core and one common runner with four operating modes:
`pr`, `health`, `production`, and `debug`.

- PR checks run the complete test suite without scraping external sites.
- Health checks monitor each source and can send Telegram DOWN/RECOVERED notifications.
- Production restores the previous SQLite database, isolates failed sources, and refreshes the iDNES guide and Czech athletics.
- Debug runs one source and uploads parsed/error artifacts for diagnosis.

iDNES is the TV source. Atletika.cz supplies the Czech outdoor and indoor championships
and the official YouTube links. Configure the watched competitions, teams, and IIHF
tournaments in `config/watched_sports.yaml`. IIHF is opt-in. The women's world
championship is excluded.

Run **Production Pipeline** on this branch, then **Telegram Weekly Preview** to
inspect the next week without sending a Telegram report.

See `docs/architecture.md` for architecture and operating details.

## Telegram

Configure these repository secrets to enable health notifications:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
