from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from validation.ibu_datacenter import parse_official_competitions, compare_official_start


def test_parse_official_ibu_competition_utc_start():
    xml = """<Competitions><Competition><RaceId>SB2627SWRLCP01SWSP</RaceId>
    <StartTime>2026-11-28T12:00:00Z</StartTime></Competition>
    <Competition><RaceId>invalid</RaceId><StartTime>not-a-date</StartTime></Competition>
    </Competitions>"""
    result = parse_official_competitions(xml)
    assert result == {"SB2627SWRLCP01SWSP": datetime(2026, 11, 28, 12, tzinfo=timezone.utc)}


def test_ibu_start_comparison_converts_timezones():
    official = datetime(2026, 11, 28, 12, tzinfo=timezone.utc)
    finland = datetime(2026, 11, 28, 14, tzinfo=ZoneInfo("Europe/Helsinki"))
    assert compare_official_start(finland, official)
    assert not compare_official_start(datetime(2026, 11, 28, 13, tzinfo=timezone.utc), official)
    assert not compare_official_start(datetime(2026, 11, 28, 12), official)


def test_ibu_parser_rejects_naive_time():
    xml = "<Competitions><Competition><RaceId>R1</RaceId><StartTime>2026-11-28T12:00:00</StartTime></Competition></Competitions>"
    assert parse_official_competitions(xml) == {}
