from datetime import timezone

from scrapers.biathlonworld import _parse_competitions, _is_snow_biathlon_event, _event_dates_match_calendar_label


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


def test_excludes_roller_and_summer_events():
    assert not _is_snow_biathlon_event("Loop One Festival", "Munich", "BT2627SWRLOG__")
    assert not _is_snow_biathlon_event("Summer World Championships", "Otepaa", "BT2627SWRLCH__")
    assert not _is_snow_biathlon_event("Roller Cup", "Munich", None)
    assert _is_snow_biathlon_event("World Cup", "Kontiolahti", "BT2627SWRLCP01")
    assert _is_snow_biathlon_event("World Cup", "Kontiolahti", "BT2627SWRLCP01".replace("SWRL", "WRL"))


def test_stale_calendar_races_rejected():
    races = _parse_competitions("Oct 17 2026 Sat 09:00 Women's Sprint Scheduled", "Munich", "Germany", "https://www.biathlonworld.com/calendar?EventId=test")
    assert not _event_dates_match_calendar_label("26—29 Nov 2026 Kontiolahti", races)
    assert not _event_dates_match_calendar_label("17—18 Oct 2026 Munich", races)
    assert not _event_dates_match_calendar_label("", races)


def test_loop_one_excluded_by_event_id_even_without_name():
    assert not _is_snow_biathlon_event("Munich", "Munich", "BT2627SWRLOG__")


def test_winter_event_not_excluded_by_unrelated_navigation():
    assert _is_snow_biathlon_event("World Cup Nov 2026", "Kontiolahti", "BT2627SWRLCP01")


def test_calendar_card_context_with_dates():
    races = _parse_competitions("Nov 28 2026 Sat 12:00 Women's Sprint Scheduled", "Kontiolahti", "Finland", "https://www.biathlonworld.com/calendar?EventId=BT2627SWRLCP01")
    assert _event_dates_match_calendar_label("Kontiolahti 26—29 Nov 2026 World Cup", races)


def test_winter_calendar_date_is_accepted():
    races = _parse_competitions("Nov 28 2026 Sat 12:00 Women's Sprint Scheduled", "Kontiolahti", "Finland", "https://www.biathlonworld.com/calendar?EventId=BT2627SWRLCP01")
    assert _event_dates_match_calendar_label("26—29 Nov 2026 Kontiolahti", races)


def test_official_ibu_races_use_utc_and_race_ids(monkeypatch):
    import json
    from scrapers.biathlonworld import _official_event_races

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, size):
            return json.dumps([
                {"RaceId": "BT2627SWRLCP01SMIN", "StartTime": "2026-11-26T15:15:00Z"},
                {"RaceId": "BT2627SWRLCP01SWIN", "StartTime": "2026-11-27T15:15:00Z"},
            ]).encode()

    monkeypatch.setattr("scrapers.biathlonworld.urlopen", lambda request, timeout: Response())
    events = _official_event_races("BT2627SWRLCP01", "Kontiolahti", "Finland", "https://example.com")
    assert [e.source_id for e in events] == ["BT2627SWRLCP01SMIN", "BT2627SWRLCP01SWIN"]
    assert events[0].start_datetime.isoformat() == "2026-11-26T15:15:00+00:00"
    assert events[0].timezone == "Europe/Helsinki"


def test_official_ibu_rejects_empty_schedule(monkeypatch):
    import pytest
    from scrapers.biathlonworld import _official_event_races

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, size):
            return b"[]"

    monkeypatch.setattr("scrapers.biathlonworld.urlopen", lambda request, timeout: Response())
    with pytest.raises(RuntimeError, match="no usable official races"):
        _official_event_races("BT2627SWRLCP01", "Kontiolahti", "Finland", "https://example.com")


def test_official_ibu_extended_race_codes():
    from scrapers.biathlonworld import RACE_CODES
    assert RACE_CODES["SMSP2"] == "Men's Sprint 2"
    assert RACE_CODES["SWSP2"] == "Women's Sprint 2"
    assert RACE_CODES["SMM6"] == "Men's Mass Start 60"
    assert RACE_CODES["SWM6"] == "Women's Mass Start 60"
