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


def test_parse_json_ibu_competitions():
    payload = '{"Competitions":[{"RaceId":"R1","StartTime":"2026-11-28T12:00:00Z"},{"RaceId":"R2","StartTime":"2026-11-28T12:00:00+02:00"}]}'
    result = parse_official_competitions(payload)
    assert result["R1"] == datetime(2026, 11, 28, 12, tzinfo=timezone.utc)
    assert result["R2"] == datetime(2026, 11, 28, 10, tzinfo=timezone.utc)


def test_parse_json_ibu_rejects_naive_and_invalid_times():
    payload = '[{"RaceId":"R1","StartTime":"2026-11-28T12:00:00"},{"RaceId":"R2","StartTime":"invalid"}]'
    assert parse_official_competitions(payload) == {}


def test_parse_json_ibu_rejects_invalid_document():
    import pytest
    with pytest.raises(ValueError):
        parse_official_competitions('{"Competitions":')
