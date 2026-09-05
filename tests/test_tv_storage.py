from datetime import datetime, timezone

from models.tv_program import TVProgram
from storage.sqlite import SQLiteStorage


def test_tv_program_upsert_updates_existing_row(tmp_path):
    db = tmp_path / "events.db"
    storage = SQLiteStorage(str(db))
    try:
        base = dict(
            source="idnes",
            source_id="107986263",
            channel="ČT sport",
            title="Atletika: Diamantová liga 2026",
            start_datetime=datetime(2026, 9, 5, 18, 30, tzinfo=timezone.utc),
            end_datetime=datetime(2026, 9, 5, 20, 5, tzinfo=timezone.utc),
            source_url="https://tvprogram.idnes.cz/ct-4-sport/x.id107986263",
            discovered_at=datetime(2026, 9, 3, 20, 0, tzinfo=timezone.utc),
            timezone="Europe/Prague",
            distribution="tv",
        )
        storage.upsert_tv_program(TVProgram(description="first", **base))
        storage.upsert_tv_program(TVProgram(description="updated", **base))
        rows = storage.conn.execute(
            "SELECT description, timezone, distribution FROM tv_programs"
        ).fetchall()
        assert rows == [("updated", "Europe/Prague", "tv")]
    finally:
        storage.close()
