from datetime import timezone

from scrapers.biathlonworld import _parse_competitions
from scrapers.iihf import _parse_schedule


def test_biathlon_converts_local_time_to_utc():
    text = "Oct 17 2026 Sat 11:00 WOMEN'S SUPER SPRINT QUAL. Scheduled"
    event = _parse_competitions(
        text,
        location="Munich",
        country="Germany",
        source_url="https://example.com?EventId=X",
    )[0]

    assert event.timezone == "Europe/Berlin"
    assert event.start_datetime.tzinfo == timezone.utc
    # Munich is UTC+2 on 17 October 2026.
    assert event.start_datetime.hour == 9


def test_iihf_converts_local_time_to_utc():
    text = "15 May FIN vs GER Swiss Life Arena 16:20"
    event = _parse_schedule(
        text,
        year=2026,
        competition="IIHF World Championship",
        country="SWITZERLAND",
        source_url="https://example.com",
    )[0]

    assert event.timezone == "Europe/Zurich"
    assert event.start_datetime.tzinfo == timezone.utc
    # Zurich is UTC+2 in May.
    assert event.start_datetime.hour == 14
