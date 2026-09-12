import sqlite3

from matching.tv_matcher import score_pair


def row(**kwargs):
    base = dict(
        id=1,
        sport="hockey",
        competition="Tipsport extraliga",
        name="HC Dynamo Pardubice - Mountfield HK",
        location=None,
        country="CZ",
        start_datetime="2026-09-16T16:00:00+00:00",
        end_datetime=None,
        channel="Oneplay Sport 2",
        title="Tipsport extraliga",
        description=None,
    )
    base.update(kwargs)
    keys = list(base)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE x (" + ",".join(f'\"{k}\" TEXT' for k in keys) + ")")
    conn.execute(
        "INSERT INTO x (" + ",".join(f'\"{k}\"' for k in keys) + ") VALUES (" + ",".join("?" for _ in keys) + ")",
        tuple(base[k] for k in keys),
    )
    return conn.execute("SELECT * FROM x").fetchone()


def test_oneplay_multigame_block_matches_dynamo_mountfield():
    event = row()
    tv = row(
        id=2,
        start_datetime="2026-09-16T15:15:00+00:00",
        end_datetime="2026-09-16T19:15:00+00:00",
        description=(
            "Přímý přenos Tipsport extraligy. MD6: Oneplay Sport MD7 - ELH: "
            "HC Dynamo Pardubice-Mountfield HK; Oneplay Sport MD2 - ELH: "
            "Banes Motor České Budějovice-BK Mladá Boleslav"
        ),
    )
    result = score_pair(event, tv)
    assert result.status == "match"
    assert result.score >= 80
    assert "participants" in result.reasons


def test_oneplay_multigame_block_matches_verva_litvinov_short_name():
    event = row(
        name="HC Verva Litvínov - HC Dynamo Pardubice",
        start_datetime="2026-09-18T15:30:00+00:00",
    )
    tv = row(
        id=2,
        start_datetime="2026-09-18T14:45:00+00:00",
        end_datetime="2026-09-18T18:45:00+00:00",
        description=(
            "Přímý přenos Tipsport extraligy. MD8: Oneplay Sport MD7 - ELH: "
            "Rytíři Kladno-HC Sparta Praha; Oneplay Sport MD4 - ELH: "
            "HC Litvínov-HC Dynamo Pardubice"
        ),
    )
    result = score_pair(event, tv)
    assert result.status == "match"
    assert result.score >= 80
    assert "participants" in result.reasons


def test_oneplay_multigame_block_still_rejects_unlisted_fixture():
    event = row(name="HC Dynamo Pardubice - Mountfield HK")
    tv = row(
        id=2,
        start_datetime="2026-09-16T15:15:00+00:00",
        end_datetime="2026-09-16T19:15:00+00:00",
        description=(
            "Přímý přenos Tipsport extraligy. MD3: Oneplay Sport MD4 - ELH: "
            "HC Litvínov-HC Kometa Brno; Oneplay Sport MD5 - ELH: "
            "HC Vítkovice Ridera-Rytíři Kladno"
        ),
    )
    result = score_pair(event, tv)
    assert result.status == "no_match"
    assert result.score == 0
    assert result.reasons == ("team_conflict",)
