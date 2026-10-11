from datetime import datetime, timedelta, timezone

from models.sports_event import SportsEvent
from storage.sqlite import SQLiteStorage


def event(source_id: str, start: datetime, source: str = "hcdynamo") -> SportsEvent:
    return SportsEvent(
        source=source, source_id=source_id, sport="ice_hockey",
        competition="Extraliga", name=source_id, start_datetime=start,
        end_datetime=None, location=None, country="CZ",
        source_url="https://www.hcdynamo.cz/matches/MUZ",
        discovered_at=datetime.now(timezone.utc), timezone="Europe/Prague",
    )


def test_reconcile_removes_only_stale_future_dynamo(tmp_path):
    storage = SQLiteStorage(str(tmp_path / "events.db"))
    now = datetime.now(timezone.utc)
    old = event("old", now - timedelta(days=2))
    stale = event("stale", now + timedelta(days=2))
    current = event("current", now + timedelta(days=3))
    other = event("other", now + timedelta(days=4), "iihf")
    for item in (old, stale, current, other):
        storage.upsert(item)
    assert storage.reconcile_hcdynamo([]) == 0
    assert storage.reconcile_hcdynamo([current]) == 1
    rows = storage.conn.execute("SELECT source_id FROM sports_events").fetchall()
    assert {row[0] for row in rows} == {"old", "current", "other"}
    storage.close()


def test_reconcile_rejects_mixed_sources(tmp_path):
    storage = SQLiteStorage(str(tmp_path / "events.db"))
    now = datetime.now(timezone.utc)
    stale = event("stale", now + timedelta(days=2))
    storage.upsert(stale)
    assert storage.reconcile_hcdynamo([event("new", now + timedelta(days=3)), event("foreign", now + timedelta(days=4), "iihf")]) == 0
    assert storage.conn.execute("SELECT COUNT(*) FROM sports_events").fetchone()[0] == 1
    storage.close()
