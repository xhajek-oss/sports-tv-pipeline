# sports-tv-pipeline

Resilient Level 5 sports and TV data pipeline.

The project uses one shared Python core and one common runner with four operating modes:
`pr`, `health`, `production`, and `debug`.

- PR checks run the complete test suite without scraping external sites.
- Health checks monitor each source and can send Telegram DOWN/RECOVERED notifications.
- Production restores the previous SQLite database, isolates failed sources, validates data, and runs TV matching.
- Debug runs one source and uploads parsed/error artifacts for diagnosis.

See `docs/architecture.md` for architecture and operating details.

## Telegram

Configure these repository secrets to enable health notifications:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
