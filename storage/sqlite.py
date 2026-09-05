import sqlite3
from pathlib import Path

from models.sports_event import SportsEvent
from models.tv_program import TVProgram


class SQLiteStorage:
    def __init__(self, path: str = "data/sports_events.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self._create_schema()

    def _column_names(self, table: str) -> set[str]:
        return {row[1] for row in self.conn.execute(f"PRAGMA table_info({table})")}

    def _add_column_if_missing(self, table: str, column: str, definition: str) -> None:
        if column not in self._column_names(table):
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _create_schema(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sports_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                source_id TEXT,
                sport TEXT NOT NULL,
                competition TEXT NOT NULL,
                name TEXT NOT NULL,
                start_datetime TEXT NOT NULL,
                end_datetime TEXT,
                location TEXT,
                country TEXT,
                source_url TEXT NOT NULL,
                discovered_at TEXT NOT NULL,
                timezone TEXT,
                UNIQUE(source, source_id, start_datetime, name)
            )
            """
        )
        # Safe migration for databases created before venue timezone was stored.
        self._add_column_if_missing("sports_events", "timezone", "TEXT")

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tv_programs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                source_id TEXT,
                channel TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                start_datetime TEXT NOT NULL,
                end_datetime TEXT,
                source_url TEXT NOT NULL,
                discovered_at TEXT NOT NULL,
                timezone TEXT NOT NULL DEFAULT 'Europe/Prague',
                distribution TEXT NOT NULL DEFAULT 'tv',
                UNIQUE(source, source_id, start_datetime, channel)
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tv_programs_start ON tv_programs(start_datetime)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tv_programs_channel_start ON tv_programs(channel, start_datetime)"
        )
        self.conn.commit()

    def upsert(self, event: SportsEvent):
        self.conn.execute(
            """
            INSERT INTO sports_events (
                source, source_id, sport, competition, name,
                start_datetime, end_datetime, location, country,
                source_url, discovered_at, timezone
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, source_id, start_datetime, name) DO UPDATE SET
                sport=excluded.sport,
                competition=excluded.competition,
                end_datetime=excluded.end_datetime,
                location=excluded.location,
                country=excluded.country,
                source_url=excluded.source_url,
                discovered_at=excluded.discovered_at,
                timezone=excluded.timezone
            """,
            (
                event.source,
                event.source_id,
                event.sport,
                event.competition,
                event.name,
                event.start_datetime.isoformat(),
                event.end_datetime.isoformat() if event.end_datetime else None,
                event.location,
                event.country,
                event.source_url,
                event.discovered_at.isoformat(),
                getattr(event, "timezone", None),
            ),
        )
        self.conn.commit()

    def upsert_tv_program(self, program: TVProgram):
        self.conn.execute(
            """
            INSERT INTO tv_programs (
                source, source_id, channel, title, description,
                start_datetime, end_datetime, source_url, discovered_at,
                timezone, distribution
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, source_id, start_datetime, channel) DO UPDATE SET
                title=excluded.title,
                description=excluded.description,
                end_datetime=excluded.end_datetime,
                source_url=excluded.source_url,
                discovered_at=excluded.discovered_at,
                timezone=excluded.timezone,
                distribution=excluded.distribution
            """,
            (
                program.source,
                program.source_id,
                program.channel,
                program.title,
                program.description,
                program.start_datetime.isoformat(),
                program.end_datetime.isoformat() if program.end_datetime else None,
                program.source_url,
                program.discovered_at.isoformat(),
                program.timezone,
                program.distribution,
            ),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
