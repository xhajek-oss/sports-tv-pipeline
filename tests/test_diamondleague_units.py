from datetime import timezone

from scrapers.diamondleague import _extract_swiss_timing_units


def test_extracts_only_diamond_units_and_converts_epoch_to_brussels_time():
    meeting = {
        "year": 2026,
        "month": 9,
        "day": 4,
        "end_day": 5,
        "city": "Brussels",
        "country": "BEL",
        "timezone": "Europe/Brussels",
    }
    payload = {
        "content": {
            "full": {
                "Units": {
                    "diamond": {
                        "Stats": {"DiamondId": "185", "DiamondType": "FINAL"},
                        "StartTime": 1788539400000,
                        "EndTime": 1788542100000,
                        "Date": "2026-09-04",
                        "EventName": "Shot Put Women",
                    },
                    "youth": {
                        "Stats": {"CompetitionName": "Youth Memorial"},
                        "StartTime": 1788537900000,
                        "Date": "2026-09-04",
                        "EventName": "100m Girls",
                    },
                }
            }
        }
    }

    rows = _extract_swiss_timing_units(payload, meeting)

    assert len(rows) == 1
    name, start, end = rows[0]
    assert name == "Shot Put Women"
    assert start.isoformat() == "2026-09-04T18:30:00+02:00"
    assert start.astimezone(timezone.utc).isoformat() == "2026-09-04T16:30:00+00:00"
    assert end is not None
