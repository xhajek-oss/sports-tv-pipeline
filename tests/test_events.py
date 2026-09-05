from datetime import datetime, timezone

from models.sports_event import SportsEvent


def test_sports_event():
    now = datetime.now(timezone.utc)

    event = SportsEvent(
        source="test",
        source_id="1",
        sport="ice_hockey",
        competition="Test",
        name="Team A - Team B",
        start_datetime=now,
        end_datetime=None,
        location="Prague",
        country="CZ",
        source_url="https://example.com",
        discovered_at=now,
    )

    assert event.source == "test"
    assert event.sport == "ice_hockey"
