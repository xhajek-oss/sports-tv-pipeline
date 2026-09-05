from datetime import timezone

from scrapers.diamondleague import _extract_calendar, _walk_schedule


def test_calendar_keeps_date_range():
    text = "Calendar 2026 04-05 September Brussels (BEL)"
    meetings = _extract_calendar(text, 2026)
    assert len(meetings) == 1
    assert meetings[0]["day"] == 4
    assert meetings[0]["end_day"] == 5
    assert meetings[0]["timezone"] == "Europe/Brussels"


def test_schedule_extracts_iso_datetime():
    meeting = {
        "year": 2026, "month": 9, "day": 4, "end_day": 5,
        "city": "Brussels", "country": "BEL", "timezone": "Europe/Brussels",
    }
    payload = {
        "schedule": [
            {"eventName": "100m Men", "startDateTime": "2026-09-04T20:14:00"},
            {"eventName": "100m Women", "startDateTime": "2026-09-05T20:15:00"},
        ]
    }
    rows = _walk_schedule(payload, meeting)
    assert [name for name, _ in rows] == ["100m Men", "100m Women"]
    assert rows[0][1].astimezone(timezone.utc).hour == 18
    assert rows[1][1].astimezone(timezone.utc).hour == 18


def test_multiday_time_without_date_is_rejected():
    meeting = {
        "year": 2026, "month": 9, "day": 4, "end_day": 5,
        "city": "Brussels", "country": "BEL", "timezone": "Europe/Brussels",
    }
    payload = {"eventName": "100m Men", "startTime": "20:14"}
    assert _walk_schedule(payload, meeting) == []
