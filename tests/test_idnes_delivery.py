from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from delivery.digest import build_today_digest
from delivery.weekly import build_next_week_report
from matching.idnes_rules import classify
from models.sports_event import SportsEvent
from models.tv_program import TVProgram
from storage.sqlite import SQLiteStorage

PRAGUE = ZoneInfo("Europe/Prague")
ONEPLAY = (
    "Přímý přenos Tipsport extraligy. MD8: "
    "Oneplay Sport MD7 - ELH: HC Dynamo Pardubice-HC Kometa Brno; "
    "Oneplay Sport MD2 - ELH: HC Oceláři Třinec-Bílí Tygři Liberec; "
    "Oneplay Sport MD10 - ELH: HC Dynamo Pardubice-HC Kometa Brno"
)


def test_weekly_and_daily_render_idnes_without_organizer_events(tmp_path):
    db = tmp_path / "sports.db"
    start = datetime(2026, 11, 13, 16, 45, tzinfo=PRAGUE).astimezone(timezone.utc)
    storage = SQLiteStorage(db)
    storage.upsert(SportsEvent(
        "hcdynamo", "stale", "ice_hockey", "Liga mistrů", "Starý zápas", start,
        None, None, None, "https://example.test", start,
    ))
    storage.upsert_tv_program(TVProgram(
        "idnes", "old", "ČT sport", "Starý pořad", None, start, None, "https://example.test", start,
    ))
    storage.replace_idnes_programs([TVProgram(
        "idnes", "oneplay", "Oneplay Sport 2", "Tipsport extraliga", ONEPLAY,
        start, None, "https://tvprogram.idnes.cz/oneplaysport-2", start,
    )])
    assert storage.conn.execute("SELECT source_id FROM tv_programs").fetchall() == [("oneplay",)]
    storage.close()

    weekly = build_next_week_report(db, now=datetime(2026, 11, 7, 12, tzinfo=PRAGUE))
    daily = build_today_digest(db, now=start)
    for report in (weekly, daily):
        assert report is not None
        assert report.count("HC Dynamo Pardubice – HC Kometa Brno") == 1
        assert "16:45" in report
        assert "Oneplay Sport MD7" in report and "Oneplay Sport MD10" in report
        assert "Třinec" not in report and "Starý zápas" not in report


def test_successful_empty_idnes_guide_clears_stale_rows_only(tmp_path):
    storage = SQLiteStorage(tmp_path / "sports.db")
    start = datetime(2026, 11, 13, tzinfo=timezone.utc)
    for source in ("idnes", "czechathletics_youtube"):
        storage.upsert_tv_program(TVProgram(
            source, source, "Channel", "Title", None, start, None, "https://example.test", start,
        ))
    storage.replace_idnes_programs([])
    assert storage.conn.execute("SELECT source FROM tv_programs").fetchall() == [
        ("czechathletics_youtube",),
    ]
    storage.close()


def test_replays_studios_and_unselected_iihf_are_excluded():
    assert classify("Hokej: MS v ledním hokeji žen", "USA - Česko. Přímý přenos.") == []
    assert classify("Hokej: MS v ledním hokeji mužů", "USA - Česko. Přímý přenos.") == []
    assert classify("Studio hokej: Tipsport ELH", ONEPLAY) == []
    assert classify("ELH: HC Dynamo Pardubice - HC Kometa Brno", "Záznam.", live=True) == []
    assert classify("Hokej: Tipsport ELH", "HC Sparta Praha - HC Kometa Brno. Přímý přenos.") == []


def test_biathlon_and_international_athletics_rules():
    for title, detail, label in [
        ("Biatlon: SP v biatlonu", "Přímý přenos sprintu žen (Kontiolahti)", "Světový pohár"),
        ("Atletika: Diamantová liga 2026", "Přímý přenos mítinku (Řím)", "Diamond League"),
    ]:
        selection, = classify(title, detail)
        assert selection.rule.label == label
    assert classify("Biatlon: letní MS v biatlonu", "Přímý přenos závodu") == []


def test_czech_athletics_youtube_is_still_independent(tmp_path):
    db = tmp_path / "sports.db"
    start = datetime(2026, 11, 14, 8, tzinfo=PRAGUE).astimezone(timezone.utc)
    storage = SQLiteStorage(db)
    storage.upsert(SportsEvent(
        "atletika_cz", "mcr", "athletics", "Mistrovství ČR", "Mistrovství ČR – 1. den",
        start, None, "Praha", "CZ", "https://www.atletika.cz/", start,
    ))
    storage.upsert_tv_program(TVProgram(
        "czechathletics_youtube", "stream", "YouTube", "Mistrovství ČR – 1. den",
        "Oficiální ČAS stream: Mistrovství ČR", start, None, "https://youtu.be/test",
        start, distribution="online",
    ))
    storage.close()

    weekly = build_next_week_report(db, now=datetime(2026, 11, 7, 12, tzinfo=PRAGUE))
    daily = build_today_digest(db, now=start)
    assert weekly is not None and "💻 YouTube" in weekly
    assert daily is not None and "💻 YouTube" in daily


def test_hockey_fixture_preserves_hyphenated_opponent_and_normalizes_dynamo():
    first, = classify("Tipsport ELH", "HC Frýdek-Místek – HC Dynamo Pardubice. Přímý přenos")
    second, = classify("Tipsport ELH", "Pardubice-HC Frýdek-Místek. Přímý přenos")

    assert first.name == "HC Frýdek-Místek – HC Dynamo Pardubice"
    assert first.key == second.key
    assert not classify("Tipsport ELH", "HC Dynamo Pardubice B – HC Kometa Brno. Přímý přenos")


def test_additional_competition_aliases_keep_the_same_sport_and_live_checks():
    for title, summary, expected in [
        ("Biatlon: ME 2026", "Přímý přenos sprintu žen", "biathlon_others"),
        ("ZOH 2026: Biatlon", "Přímý přenos sprintu žen", "biathlon_others"),
        ("Atletika: Atletika ČR 2026", "HMČR Ostrava. Přímý přenos", "czech_athletics_indoor"),
    ]:
        selection, = classify(title, summary)
        assert selection.rule.id == expected
    assert not classify("Biatlon: ME 2026 juniorů", "Přímý přenos sprintu žen")
    assert not classify("ZOH 2026: Běh na lyžích", "Přímý přenos sprintu žen")
    assert not classify("Atletika: Atletika ČR 2026", "HMČR Ostrava. Záznam")
