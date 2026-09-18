import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from matching.tv_matcher import score_pair


def row(**kwargs):
    base = dict(
        id=1,
        sport="athletics",
        competition="World Athletics Ultimate Championship",
        name="400m Hurdles Women",
        location="Budapest",
        country="Hungary",
        start_datetime="2026-09-12T16:15:00+00:00",
        end_datetime=None,
        channel="ČT2",
        title="Atletika: World Athletics Ultimate Championship 2026",
        description=None,
    )
    base.update(kwargs)
    keys = list(base)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    schema = ",".join(f'"{k}" TEXT' for k in keys)
    conn.execute(f"CREATE TABLE x ({schema})")
    cols = ",".join(f'"{k}"' for k in keys)
    placeholders = ",".join("?" for _ in keys)
    conn.execute(
        f"INSERT INTO x ({cols}) VALUES ({placeholders})",
        tuple(base[k] for k in keys),
    )
    return conn.execute("SELECT * FROM x").fetchone()


def test_broad_athletics_block_matches_specific_event():
    event = row()
    tv = row(id=2, start_datetime="2026-09-12T16:00:00+00:00")
    result = score_pair(event, tv)
    assert result.score >= 70
    assert result.status == "match"
    assert "time_overlap" in result.reasons


def test_athletics_can_use_description_as_evidence():
    event = row(
        competition="Diamond League",
        name="100m Women",
        location="Brussels",
        start_datetime="2026-09-18T18:10:00+00:00",
    )
    tv = row(
        id=2,
        title="Sportovní přenos",
        description="Atletika: Diamantová liga Brusel, 100 m ženy",
        start_datetime="2026-09-18T18:00:00+00:00",
        end_datetime="2026-09-18T20:00:00+00:00",
    )
    result = score_pair(event, tv)
    assert result.status == "match"
    assert "discipline" in result.reasons
    assert "gender:women" in result.reasons


def test_biathlon_can_use_description_as_evidence():
    event = row(
        sport="biathlon",
        competition="International Biathlon Union",
        name="Women 7.5 km Sprint",
        location="Hochfilzen",
        country="Austria",
        start_datetime="2026-12-11T13:30:00+00:00",
    )
    tv = row(
        id=2,
        channel="Eurosport 1",
        title="Zimní sporty",
        description="Biatlon: SP Hochfilzen - sprint žen",
        start_datetime="2026-12-11T13:20:00+00:00",
        end_datetime="2026-12-11T15:00:00+00:00",
    )
    result = score_pair(event, tv)
    assert result.status == "match"
    assert "sport:biathlon" in result.reasons
    assert "discipline" in result.reasons
    assert "gender:women" in result.reasons
    assert "location" in result.reasons


def test_wrong_sport_is_rejected():
    event = row()
    tv = row(
        id=2,
        channel="Oneplay Sport 2",
        title="ELH: HC Dynamo Pardubice - Mountfield HK",
        description="Hokej",
        start_datetime="2026-09-12T16:00:00+00:00",
    )
    result = score_pair(event, tv)
    assert result.status == "no_match"
    assert result.score == 0


def test_far_time_is_rejected():
    event = row()
    tv = row(id=2, start_datetime="2026-09-13T12:00:00+00:00")
    result = score_pair(event, tv)
    assert result.status == "no_match"


def test_specific_hockey_broadcast_with_wrong_teams_is_rejected():
    event = row(
        sport="hockey",
        competition="ELH",
        name="HC Dynamo Pardubice - Mountfield HK",
        location="Pardubice",
        country="Czechia",
        start_datetime="2026-09-16T16:00:00+00:00",
    )
    tv = row(
        id=2,
        channel="Oneplay Sport 3",
        title="ELH: HC Olomouc - HC Sparta Praha",
        description="Hokej",
        start_datetime="2026-09-16T15:50:00+00:00",
    )
    result = score_pair(event, tv)
    assert result.score == 0
    assert result.status == "no_match"
    assert result.reasons == ("team_conflict",)


def test_specific_hockey_broadcast_with_same_teams_matches_even_reversed():
    event = row(
        sport="hockey",
        competition="ELH",
        name="HC Dynamo Pardubice - Mountfield HK",
        location="Pardubice",
        country="Czechia",
        start_datetime="2026-09-16T16:00:00+00:00",
    )
    tv = row(
        id=2,
        channel="Oneplay Sport 2",
        title="ELH: Mountfield HK - HC Dynamo Pardubice",
        description="Hokej",
        start_datetime="2026-09-16T15:50:00+00:00",
    )
    result = score_pair(event, tv)
    assert result.status == "match"
    assert result.score >= 70
    assert "participants" in result.reasons


def test_generic_hockey_title_uses_matchup_from_description():
    event = row(
        sport="hockey",
        competition="ELH",
        name="HC Dynamo Pardubice - HC Energie Karlovy Vary",
        location="Pardubice",
        country="Czechia",
        start_datetime="2026-09-20T15:00:00+00:00",
    )
    tv = row(
        id=2,
        channel="Oneplay Sport 3",
        title="Tipsport extraliga",
        description="HC Dynamo Pardubice - HC Energie Karlovy Vary",
        start_datetime="2026-09-20T14:50:00+00:00",
        end_datetime="2026-09-20T17:30:00+00:00",
    )
    result = score_pair(event, tv)
    assert result.status == "match"
    assert result.score >= 80
    assert "participants" in result.reasons
    assert "competition:extraliga" in result.reasons


def test_multigame_hockey_block_matches_only_listed_fixture():
    event = row(
        sport="hockey",
        competition="ELH",
        name="HC Dynamo Pardubice - HC Energie Karlovy Vary",
        start_datetime="2026-09-20T15:00:00+00:00",
    )
    tv = row(
        id=2,
        channel="Oneplay Sport 3",
        title="Tipsport extraliga",
        description="HC Kometa Brno - Mountfield HK; HC Sparta Praha - HC Oceláři Třinec",
        start_datetime="2026-09-20T14:50:00+00:00",
        end_datetime="2026-09-20T17:30:00+00:00",
    )
    result = score_pair(event, tv)
    assert result.status == "no_match"
    assert result.score == 0
    assert result.reasons == ("team_conflict",)


def test_chl_saipa_idnes_salpa_typo_matches():
    event = row(
        sport="hockey",
        competition="Liga Mistrů",
        name="SaiPa Lappeenranta - HC Dynamo Pardubice",
        location="Lappeenranta",
        country="Finland",
        start_datetime="2026-09-10T15:30:00+00:00",
    )
    tv = row(
        id=2,
        channel="Sport1",
        title="Lední hokej: Salpa - Dynamo Pardubice",
        description="Přímý přenos utkání, CHL, základní část",
        start_datetime="2026-09-10T15:30:00+00:00",
        end_datetime="2026-09-10T18:00:00+00:00",
    )
    result = score_pair(event, tv)
    assert result.status == "match"
    assert result.score >= 70
    assert "participants" in result.reasons


def test_chl_kookoo_city_suffix_matches_short_tv_name():
    event = row(
        sport="hockey",
        competition="Liga Mistrů",
        name="KooKoo Kouvola - HC Dynamo Pardubice",
        location="Kouvola",
        country="Finland",
        start_datetime="2026-09-12T14:00:00+00:00",
    )
    tv = row(
        id=2,
        channel="Sport2",
        title="Lední hokej: KooKoo - Dynamo Pardubice",
        description="Přímý přenos utkání, CHL, základní část",
        start_datetime="2026-09-12T14:00:00+00:00",
        end_datetime="2026-09-12T16:30:00+00:00",
    )
    result = score_pair(event, tv)
    assert result.status == "match"
    assert result.score >= 70
    assert "participants" in result.reasons


def test_generic_city_suffix_shortening_matches_without_alias_table():
    event = row(
        sport="hockey",
        competition="CHL",
        name="Tappara Tampere - Fribourg Gotteron",
        start_datetime="2026-10-01T16:00:00+00:00",
    )
    tv = row(
        id=2,
        channel="Sport2",
        title="Hokej: Tappara - Fribourg Gotteron",
        description="CHL",
        start_datetime="2026-10-01T16:00:00+00:00",
        end_datetime="2026-10-01T18:30:00+00:00",
    )
    result = score_pair(event, tv)
    assert result.status == "match"
    assert "participants" in result.reasons


def test_generic_single_character_team_typo_matches():
    event = row(
        sport="hockey",
        competition="CHL",
        name="Ilves Tampere - Dynamo Pardubice",
        start_datetime="2026-10-02T16:00:00+00:00",
    )
    tv = row(
        id=2,
        channel="Sport1",
        title="Hokej: llves - Dynamo Pardubice",
        description="CHL",
        start_datetime="2026-10-02T16:00:00+00:00",
        end_datetime="2026-10-02T18:30:00+00:00",
    )
    result = score_pair(event, tv)
    assert result.status == "match"
    assert "participants" in result.reasons


def test_fuzzy_matching_does_not_confuse_different_prague_clubs():
    event = row(
        sport="hockey",
        competition="ELH",
        name="HC Sparta Praha - HC Dynamo Pardubice",
        start_datetime="2026-10-03T16:00:00+00:00",
    )
    tv = row(
        id=2,
        channel="ČT sport",
        title="Hokej: HC Slavia Praha - HC Dynamo Pardubice",
        description="ELH",
        start_datetime="2026-10-03T16:00:00+00:00",
        end_datetime="2026-10-03T18:30:00+00:00",
    )
    result = score_pair(event, tv)
    assert result.status == "no_match"
    assert result.score == 0
    assert result.reasons == ("team_conflict",)


def test_generic_hockey_block_is_not_enough_for_overlapping_same_competition_games(tmp_path):
    db = tmp_path / "matcher.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE sports_events (
            id INTEGER PRIMARY KEY, source TEXT, source_id TEXT, sport TEXT,
            competition TEXT, name TEXT, start_datetime TEXT, end_datetime TEXT,
            location TEXT, country TEXT, source_url TEXT, discovered_at TEXT, timezone TEXT
        );
        CREATE TABLE tv_programs (
            id INTEGER PRIMARY KEY, source TEXT, source_id TEXT, channel TEXT,
            title TEXT, description TEXT, start_datetime TEXT, end_datetime TEXT,
            source_url TEXT, discovered_at TEXT, timezone TEXT, distribution TEXT
        );
    """)
    for event_id, name, start in (
        (1, "HC Kometa Brno - HC Dynamo Pardubice", "2026-09-27T15:00:00+00:00"),
        (2, "HC Vítkovice Ridera - BK Mladá Boleslav", "2026-09-27T14:30:00+00:00"),
    ):
        conn.execute(
            """INSERT INTO sports_events
               (id, source, source_id, sport, competition, name, start_datetime,
                end_datetime, location, country, source_url, discovered_at, timezone)
               VALUES (?, 'test', ?, 'hockey', 'ELH', ?, ?, NULL, NULL, 'Czechia',
                       '', '', 'Europe/Prague')""",
            (event_id, str(event_id), name, start),
        )
    conn.execute(
        """INSERT INTO tv_programs
           (id, source, source_id, channel, title, description, start_datetime,
            end_datetime, source_url, discovered_at, timezone, distribution)
           VALUES (1, 'idnes', 'ct2', 'ČT2', 'Hokej: Tipsport ELH 2026/2027',
                   'Přímý přenos', '2026-09-27T14:00:00+00:00',
                   '2026-09-27T17:00:00+00:00', '', '', 'Europe/Prague', 'tv')"""
    )
    conn.commit()
    conn.close()

    from matching.tv_matcher import TVMatcher
    assert TVMatcher(db).find_candidates(min_score=70) == []


def test_generic_hockey_block_can_match_when_only_one_fixture_overlaps(tmp_path):
    db = tmp_path / "matcher.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE sports_events (
            id INTEGER PRIMARY KEY, source TEXT, source_id TEXT, sport TEXT,
            competition TEXT, name TEXT, start_datetime TEXT, end_datetime TEXT,
            location TEXT, country TEXT, source_url TEXT, discovered_at TEXT, timezone TEXT
        );
        CREATE TABLE tv_programs (
            id INTEGER PRIMARY KEY, source TEXT, source_id TEXT, channel TEXT,
            title TEXT, description TEXT, start_datetime TEXT, end_datetime TEXT,
            source_url TEXT, discovered_at TEXT, timezone TEXT, distribution TEXT
        );
        INSERT INTO sports_events VALUES
          (1,'test','1','hockey','ELH','HC Kometa Brno - HC Dynamo Pardubice',
           '2026-09-27T15:00:00+00:00',NULL,NULL,'Czechia','','','Europe/Prague');
        INSERT INTO tv_programs VALUES
          (1,'idnes','ct2','ČT2','Hokej: Tipsport ELH 2026/2027','Přímý přenos',
           '2026-09-27T14:00:00+00:00','2026-09-27T17:00:00+00:00','','',
           'Europe/Prague','tv');
    """)
    conn.commit()
    conn.close()

    from matching.tv_matcher import TVMatcher
    candidates = TVMatcher(db).find_candidates(min_score=70)
    assert len(candidates) == 1
    assert candidates[0].sports_event_id == 1
