from datetime import date, datetime
from zoneinfo import ZoneInfo

from delivery.weekly import WeeklyEvent, format_weekly_report, next_week_range

PRAGUE = ZoneInfo("Europe/Prague")


def test_next_week_range_from_sunday():
    now = datetime(2026, 9, 6, 9, 0, tzinfo=PRAGUE)
    monday, sunday = next_week_range(now=now)

    assert monday == date(2026, 9, 7)
    assert sunday == date(2026, 9, 13)


def test_weekly_report_groups_events_by_day_and_sport():
    events = [
        WeeklyEvent(
            event_id=1,
            sport="hockey",
            competition="Liga mistrů",
            name="HC Dynamo Pardubice – Rögle BK",
            start=datetime(2026, 9, 7, 18, 0, tzinfo=PRAGUE),
            location=None,
            country="Česko",
        ),
        WeeklyEvent(
            event_id=2,
            sport="athletics",
            competition="World Athletics Ultimate Championship",
            name="Budapešť (Maďarsko)",
            start=datetime(2026, 9, 11, 19, 0, tzinfo=PRAGUE),
            location="Budapešť",
            country="Maďarsko",
        ),
    ]

    text = format_weekly_report(
        events,
        monday=date(2026, 9, 7),
        sunday=date(2026, 9, 13),
    )

    assert text is not None
    assert "Pondělí 7. září – Neděle 13. září" in text
    assert "Pondělí 7. září" in text
    assert "🏒 HOKEJ" in text
    assert "18:00" in text
    assert "HC Dynamo Pardubice – Rögle BK" in text
    assert "Pátek 11. září" in text
    assert "🏃 ATLETIKA" in text
    assert "Budapešť (Maďarsko)" in text


def test_weekly_report_returns_none_for_no_events():
    assert format_weekly_report([], monday=date(2026, 9, 7), sunday=date(2026, 9, 13)) is None
