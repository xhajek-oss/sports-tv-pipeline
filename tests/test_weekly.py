from datetime import date, datetime
from zoneinfo import ZoneInfo

from delivery.digest import Broadcast
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
            name="SaiPa Lappeenranta (Finsko) – HC Dynamo Pardubice",
            start=datetime(2026, 9, 10, 17, 30, tzinfo=PRAGUE),
            location=None,
            country="Finsko",
        ),
        WeeklyEvent(
            event_id=2,
            sport="athletics",
            competition="World Athletics Ultimate Championship",
            name="Budapešť (Maďarsko)",
            start=datetime(2026, 9, 11, 18, 0, tzinfo=PRAGUE),
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
    assert "Čtvrtek 10. září" in text
    assert "🏒 HOKEJ" in text
    assert "17:30" in text
    assert "SaiPa Lappeenranta (Finsko) – HC Dynamo Pardubice" in text
    assert "Pátek 11. září" in text
    assert "🏃 ATLETIKA" in text
    assert "Budapešť (Maďarsko)" in text


def test_weekly_report_shows_tv_channel_and_broadcast_time():
    tv_start = datetime(2026, 9, 10, 17, 15, tzinfo=PRAGUE)
    broadcast = Broadcast(
        event_id=1,
        sport="hockey",
        competition="Liga mistrů",
        event_name="SaiPa Lappeenranta - HC Dynamo Pardubice",
        location=None,
        country="FI",
        source_url="https://example.test",
        tv_start=tv_start,
        tv_end=None,
        channel="Sport2",
        distribution="tv",
        tv_title="Lední hokej: SaiPa Lappeenranta - Dynamo Pardubice",
    )
    event = WeeklyEvent(
        event_id=1,
        sport="hockey",
        competition="Liga mistrů",
        name="SaiPa Lappeenranta (Finsko) – HC Dynamo Pardubice",
        start=tv_start,
        location=None,
        country="Finsko",
        broadcasts=(broadcast,),
    )

    text = format_weekly_report(
        [event], monday=date(2026, 9, 7), sunday=date(2026, 9, 13)
    )

    assert text is not None
    assert "<b>17:15</b>" in text
    assert "📺 Sport2" in text


def test_weekly_report_keeps_event_without_tv_channel():
    event = WeeklyEvent(
        event_id=2,
        sport="hockey",
        competition="Liga mistrů",
        name="KooKoo Kouvola (Finsko) – HC Dynamo Pardubice",
        start=datetime(2026, 9, 12, 16, 0, tzinfo=PRAGUE),
        location=None,
        country="Finsko",
    )

    text = format_weekly_report(
        [event], monday=date(2026, 9, 7), sunday=date(2026, 9, 13)
    )

    assert text is not None
    assert "KooKoo Kouvola (Finsko) – HC Dynamo Pardubice" in text
    assert "📺" not in text


def test_weekly_report_returns_none_for_no_events():
    assert format_weekly_report([], monday=date(2026, 9, 7), sunday=date(2026, 9, 13)) is None
