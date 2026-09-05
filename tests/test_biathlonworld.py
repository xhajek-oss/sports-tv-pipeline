from datetime import timezone

from scrapers.biathlonworld import _parse_competitions


def test_biathlonworld_parser():
    text = """
    Upcoming competitions

    Oct 17 2026 Sat 09:00
    Women's Super Sprint Qual.
    Scheduled

    Oct 17 2026 Sat 10:20
    Men's Super Sprint Qual.
    Scheduled

    Oct 17 2026 Sat 13:45
    Women's Super Sprint Final
    Scheduled
    """

    events = _parse_competitions(
        text=text,
        location="Munich",
        country="Germany",
        source_url=(
            "https://www.biathlonworld.com/calendar?"
            "EventId=BT2627SWRLOG__&SeasonId=2627"
        ),
    )

    assert len(events) == 3
    assert events[0].source == "biathlonworld"
    assert events[0].sport == "biathlon"
    assert events[0].name == "Women's Super Sprint Qual."
    assert events[0].location == "Munich"
    assert events[0].country == "Germany"
    assert events[0].timezone == "Europe/Berlin"
    assert events[0].start_datetime.tzinfo == timezone.utc
    assert events[0].start_datetime.isoformat() == "2026-10-17T07:00:00+00:00"

    assert events[1].name == "Men's Super Sprint Qual."
    assert events[1].start_datetime.isoformat() == "2026-10-17T08:20:00+00:00"
