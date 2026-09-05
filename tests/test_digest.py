from datetime import date, datetime
from zoneinfo import ZoneInfo

from delivery.digest import Broadcast, DigestItem, _biathlon_name_cs, _is_replay, format_digest

PRAGUE = ZoneInfo("Europe/Prague")


def broadcast(*, start: str, channel: str, distribution: str = "tv") -> Broadcast:
    dt = datetime.fromisoformat(start).replace(tzinfo=PRAGUE)
    return Broadcast(
        event_id=1,
        sport="hockey",
        competition="Liga mistrů",
        event_name="HC Dynamo Pardubice - Rögle BK",
        location=None,
        country=None,
        source_url="https://example.test",
        tv_start=dt,
        tv_end=None,
        channel=channel,
        distribution=distribution,
        tv_title="Hokej",
    )


def test_replay_terms_are_rejected():
    assert _is_replay("Hokej: Archiv Z")
    assert _is_replay("Atletika - záznam")
    assert not _is_replay("Hokej: BULY START ŽIVĚ")


def test_biathlon_names_are_czech():
    assert _biathlon_name_cs("WOMEN'S 10KM PURSUIT") == "Stíhací závod žen 10 km"
    assert _biathlon_name_cs("MEN'S 10KM SPRINT") == "Sprint mužů 10 km"
    assert _biathlon_name_cs("SINGLE MIXED RELAY (W+M)") == "Smíšená štafeta dvojic"


def test_format_digest_uses_real_broadcast_time_and_media_types():
    tv = broadcast(start="2026-09-05T17:45:00", channel="ČT sport")
    online = broadcast(
        start="2026-09-05T17:55:00",
        channel="ČT sport Plus",
        distribution="online",
    )
    item = DigestItem(
        key="event|1",
        sport="hockey",
        competition="Liga mistrů",
        title="HC Dynamo Pardubice – Rögle BK (Švédsko)",
        location=None,
        country=None,
        start=tv.tv_start,
        broadcasts=(tv, online),
    )

    text = format_digest([item], day=date(2026, 9, 5))

    assert text is not None
    assert text.startswith("Sobota 5. září\n\n🏒 <b>HOKEJ</b>")
    assert "🏆 Liga mistrů\n<b>17:45</b>" in text
    assert "🏆 Liga mistrů\n\n<b>17:45</b>" not in text
    assert "SPORT V TV" not in text
    assert "🏒 <b>HOKEJ</b>" in text
    assert "Liga mistrů" in text
    assert "<b>17:45</b>" in text
    assert "📺 ČT sport" in text
    assert "💻 ČT sport Plus od 17:55" in text
    assert "Dnes" not in text


def test_biathlon_shared_channel_is_printed_once():
    b1 = broadcast(start="2026-12-05T11:30:00", channel="ČT sport")
    b2 = Broadcast(**{**b1.__dict__, "event_id": 2})
    first = DigestItem(
        key="event|1", sport="biathlon", competition="Světový pohár",
        title="Stíhací závod žen 10 km", location="Hochfilzen", country="Rakousko",
        start=b1.tv_start, broadcasts=(b1,),
    )
    second = DigestItem(
        key="event|2", sport="biathlon", competition="Světový pohár",
        title="Stíhací závod mužů 12,5 km", location="Hochfilzen", country="Rakousko",
        start=b2.tv_start, broadcasts=(b2,),
    )

    text = format_digest([first, second], day=date(2026, 12, 5))

    assert text is not None
    assert "Hochfilzen (Rakousko)\n<b>11:30</b>" in text
    assert text.count("📺 ČT sport") == 1
    assert text.count("Hochfilzen (Rakousko)") == 1
