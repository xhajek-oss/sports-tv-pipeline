from __future__ import annotations

import html
import re
import sqlite3
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from matching.tv_matcher import MatchCandidate, TVMatcher

PRAGUE = ZoneInfo("Europe/Prague")
UTC = timezone.utc

DAY_NAMES = (
    "Pondělí", "Úterý", "Středa", "Čtvrtek", "Pátek", "Sobota", "Neděle"
)
MONTH_NAMES = (
    "", "ledna", "února", "března", "dubna", "května", "června",
    "července", "srpna", "září", "října", "listopadu", "prosince"
)

COUNTRIES = {
    "AT": "Rakousko", "AUT": "Rakousko", "AUSTRIA": "Rakousko",
    "BE": "Belgie", "BEL": "Belgie", "BELGIUM": "Belgie",
    "CH": "Švýcarsko", "CHE": "Švýcarsko", "SWITZERLAND": "Švýcarsko",
    "CZ": "Česko", "CZE": "Česko", "CZECHIA": "Česko", "CZECH REPUBLIC": "Česko",
    "DE": "Německo", "DEU": "Německo", "GERMANY": "Německo",
    "DK": "Dánsko", "DNK": "Dánsko", "DENMARK": "Dánsko",
    "EE": "Estonsko", "EST": "Estonsko", "ESTONIA": "Estonsko",
    "FI": "Finsko", "FIN": "Finsko", "FINLAND": "Finsko",
    "FR": "Francie", "FRA": "Francie", "FRANCE": "Francie",
    "HU": "Maďarsko", "HUN": "Maďarsko", "HUNGARY": "Maďarsko",
    "IT": "Itálie", "ITA": "Itálie", "ITALY": "Itálie",
    "LV": "Lotyšsko", "LVA": "Lotyšsko", "LATVIA": "Lotyšsko",
    "NO": "Norsko", "NOR": "Norsko", "NORWAY": "Norsko",
    "PL": "Polsko", "POL": "Polsko", "POLAND": "Polsko",
    "RO": "Rumunsko", "ROU": "Rumunsko", "ROMANIA": "Rumunsko",
    "SE": "Švédsko", "SWE": "Švédsko", "SWEDEN": "Švédsko",
    "SI": "Slovinsko", "SVN": "Slovinsko", "SLOVENIA": "Slovinsko",
    "SK": "Slovensko", "SVK": "Slovensko", "SLOVAKIA": "Slovensko",
    "US": "USA", "USA": "USA", "UNITED STATES": "USA",
    "CA": "Kanada", "CAN": "Kanada", "CANADA": "Kanada",
}

HOCKEY_TEAM_COUNTRIES = {
    "gks tychy": "Polsko",
    "rogle bk": "Švédsko",
    "rogle angelholm": "Švédsko",
    "saipa lappeenranta": "Finsko",
    "kookoo kouvola": "Finsko",
    "bordeaux boxers": "Francie",
    "vaxjo lakers": "Švédsko",
}

CHANNEL_ALIASES = {
    "ct sport": "ČT sport",
    "ct sport hd": "ČT sport",
    "ct2": "ČT2",
    "nova sport 1 hd": "Nova Sport 1",
    "nova sport 2 hd": "Nova Sport 2",
    "oneplay sport 1 hd": "Oneplay Sport 1",
    "oneplay sport 2 hd": "Oneplay Sport 2",
    "oneplay sport 3 hd": "Oneplay Sport 3",
    "oneplay sport 4 hd": "Oneplay Sport 4",
}

REPLAY_TERMS = (
    "archiv", "zaznam", "repriza", "opakovani", "ze zaznamu"
)

SPORT_PRIORITY = {"hockey": 0, "biathlon": 1, "athletics": 2}


@dataclass(frozen=True)
class Broadcast:
    event_id: int
    sport: str
    competition: str
    event_name: str
    location: str | None
    country: str | None
    source_url: str
    tv_start: datetime
    tv_end: datetime | None
    channel: str
    distribution: str
    tv_title: str


@dataclass(frozen=True)
class DigestItem:
    key: str
    sport: str
    competition: str
    title: str
    location: str | None
    country: str | None
    start: datetime
    broadcasts: tuple[Broadcast, ...]
    event_rows: tuple[Broadcast, ...]


def _norm(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold().replace("–", "-").replace("—", "-")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _sport_name(value: str) -> str:
    n = _norm(value)
    if "hockey" in n or "hokej" in n:
        return "hockey"
    if "biathlon" in n or "biatlon" in n:
        return "biathlon"
    return "athletics"


def _country_cs(value: str | None) -> str | None:
    if not value:
        return None
    key = value.strip().upper()
    return COUNTRIES.get(key, value.title())


def _location_cs(value: str | None) -> str | None:
    if not value:
        return None
    known = {
        "BRUSSELS": "Brusel",
        "BUDAPEST": "Budapešť",
        "HOCHFILZEN": "Hochfilzen",
        "KONTIOLAHTI": "Kontiolahti",
        "LE GRAND BORNAND": "Le Grand-Bornand",
        "MUNICH": "Mnichov",
        "MÜNCHEN": "Mnichov",
        "NOVE MESTO": "Nové Město",
        "NOVÉ MĚSTO": "Nové Město",
        "OBERHOF": "Oberhof",
        "RUHPOLDING": "Ruhpolding",
        "SJUSJOEN": "Sjusjøen",
        "SJUSJØEN": "Sjusjøen",
        "IDRE FJAELL": "Idre Fjäll",
        "IDRE FJÄLL": "Idre Fjäll",
    }
    return known.get(value.strip().upper(), value.strip().title())


def _channel_name(value: str) -> str:
    normalized = _norm(value)
    if normalized in CHANNEL_ALIASES:
        return CHANNEL_ALIASES[normalized]
    normalized = re.sub(r"\s+hd$", "", normalized).strip()
    if normalized in CHANNEL_ALIASES:
        return CHANNEL_ALIASES[normalized]
    return value.strip().removesuffix(" HD")


def _is_replay(title: str) -> bool:
    text = _norm(title)
    return any(term in text for term in REPLAY_TERMS)


def _event_live_end(event: sqlite3.Row) -> datetime:
    start = _parse_dt(event["start_datetime"])
    assert start is not None
    explicit = _parse_dt(event["end_datetime"])
    if explicit:
        return explicit
    sport = _sport_name(event["sport"])
    fallback = {
        "hockey": timedelta(hours=3, minutes=30),
        "biathlon": timedelta(hours=2),
        "athletics": timedelta(hours=4),
    }[sport]
    return start + fallback


def _is_live_timing(event: sqlite3.Row, tv: sqlite3.Row) -> bool:
    event_start = _parse_dt(event["start_datetime"])
    tv_start = _parse_dt(tv["start_datetime"])
    tv_end = _parse_dt(tv["end_datetime"])
    if event_start is None or tv_start is None:
        return False
    live_end = _event_live_end(event)
    effective_tv_end = tv_end or tv_start + timedelta(hours=3)
    return tv_start <= live_end and effective_tv_end >= event_start - timedelta(hours=1)


def _competition_cs(event: Broadcast) -> str:
    value = event.competition.strip()
    n = _norm(value)
    if event.sport == "biathlon" and "biathlonworld.com" in event.source_url:
        upper_url = event.source_url.upper()
        if "SWRLCP" in upper_url:
            return "Světový pohár"
        if "SWRLCH" in upper_url:
            return "Mistrovství světa"
    mapping = {
        "liga mistru": "Liga mistrů",
        "tipsport extraliga": "Extraliga",
        "wanda diamond league": "Diamond League",
        "diamond league": "Diamond League",
        "world athletics ultimate championship": "World Athletics Ultimate Championship",
        "international biathlon union": "Biatlon",
    }
    return mapping.get(n, value)


def _biathlon_name_cs(value: str) -> str:
    text = value.upper().strip()
    gender = ""
    if text.startswith("WOMEN"):
        gender = "žen"
    elif text.startswith("MEN"):
        gender = "mužů"

    distance_match = re.search(r"(\d+(?:\.\d+)?)\s*KM", text)
    distance = ""
    if distance_match:
        distance = distance_match.group(1).replace(".5", ",5") + " km"

    if "SUPER SPRINT" in text:
        discipline = "Super sprint"
    elif "SPRINT" in text:
        discipline = "Sprint"
    elif "PURSUIT" in text:
        discipline = "Stíhací závod"
    elif "INDIVIDUAL" in text:
        discipline = "Vytrvalostní závod"
    elif "MASS START" in text:
        discipline = "Hromadný start"
    elif "SINGLE MIXED RELAY" in text:
        return "Smíšená štafeta dvojic"
    elif "MIXED RELAY" in text:
        return "Smíšená štafeta"
    elif "RELAY" in text:
        discipline = "Štafeta"
    else:
        return value.title()

    parts = [discipline]
    if gender:
        parts.append(gender)
    if distance and "RELAY" not in text:
        parts.append(distance)
    return " ".join(parts)


def _hockey_title(event: Broadcast) -> str:
    title = event.event_name.replace(" - ", " – ")
    if _norm(event.competition) != "liga mistru":
        return title
    teams = re.split(r"\s+[–-]\s+", title)
    if len(teams) != 2:
        return title
    for idx, team in enumerate(teams):
        if "dynamo pardubice" in _norm(team):
            continue
        country = HOCKEY_TEAM_COUNTRIES.get(_norm(team))
        if country:
            teams[idx] = f"{team} ({country})"
    return " – ".join(teams)


def _athletics_title(event: Broadcast) -> str:
    location = _location_cs(event.location)
    country = _country_cs(event.country)
    if location and country:
        return f"{location} ({country})"
    return location or event.event_name


def _format_date(value: date) -> str:
    return f"{DAY_NAMES[value.weekday()]} {value.day}. {MONTH_NAMES[value.month]}"


def _group_key(b: Broadcast, local_day: date) -> str:
    if b.sport == "athletics":
        return f"athletics|{_norm(b.competition)}|{_norm(b.location)}|{local_day.isoformat()}"
    return f"event|{b.event_id}"


def _dedupe_broadcasts(rows: list[Broadcast]) -> tuple[Broadcast, ...]:
    best: dict[tuple[str, str, datetime], Broadcast] = {}
    for row in rows:
        channel = _channel_name(row.channel)
        key = (row.distribution, channel, row.tv_start)
        best[key] = Broadcast(
            event_id=row.event_id,
            sport=row.sport,
            competition=row.competition,
            event_name=row.event_name,
            location=row.location,
            country=row.country,
            source_url=row.source_url,
            tv_start=row.tv_start,
            tv_end=row.tv_end,
            channel=channel,
            distribution=row.distribution,
            tv_title=row.tv_title,
        )
    return tuple(sorted(best.values(), key=lambda x: (x.tv_start, x.distribution != "tv", x.channel)))


def collect_today_items(
    db_path: str | Path = "data/sports_events.db",
    *,
    now: datetime | None = None,
) -> list[DigestItem]:
    now_local = (now or datetime.now(PRAGUE)).astimezone(PRAGUE)
    today = now_local.date()
    matcher = TVMatcher(db_path)
    candidates = [c for c in matcher.find_candidates(min_score=70) if c.status == "match"]
    details = matcher.candidate_details(candidates)

    grouped: dict[str, list[Broadcast]] = defaultdict(list)
    for candidate, event, tv in details:
        tv_start = _parse_dt(tv["start_datetime"])
        if tv_start is None or tv_start.astimezone(PRAGUE).date() != today:
            continue
        if _is_replay(tv["title"] or "") or not _is_live_timing(event, tv):
            continue
        sport = _sport_name(event["sport"])
        b = Broadcast(
            event_id=int(event["id"]),
            sport=sport,
            competition=event["competition"] or "",
            event_name=event["name"] or "",
            location=event["location"],
            country=event["country"],
            source_url=event["source_url"] or "",
            tv_start=tv_start.astimezone(PRAGUE),
            tv_end=_parse_dt(tv["end_datetime"]),
            channel=tv["channel"] or "",
            distribution=(tv["distribution"] or "tv").lower(),
            tv_title=tv["title"] or "",
        )
        grouped[_group_key(b, today)].append(b)

    items: list[DigestItem] = []
    for key, rows in grouped.items():
        broadcasts = _dedupe_broadcasts(rows)
        if not broadcasts:
            continue
        first = min(rows, key=lambda x: x.tv_start)
        if first.sport == "hockey":
            title = _hockey_title(first)
            location = None
            country = None
        elif first.sport == "biathlon":
            title = _biathlon_name_cs(first.event_name)
            location = _location_cs(first.location)
            country = _country_cs(first.country)
        else:
            title = _athletics_title(first)
            location = None
            country = None
        items.append(
            DigestItem(
                key=key,
                sport=first.sport,
                competition=_competition_cs(first),
                title=title,
                location=location,
                country=country,
                start=min(b.tv_start for b in broadcasts),
                broadcasts=broadcasts,
                event_rows=tuple(rows),
            )
        )

    return sorted(items, key=lambda x: (x.start, SPORT_PRIORITY.get(x.sport, 99), x.title))


def _media_lines(broadcasts: tuple[Broadcast, ...], main_start: datetime) -> list[str]:
    by_type: dict[str, list[str]] = {"tv": [], "online": []}
    seen: set[tuple[str, str]] = set()
    for b in broadcasts:
        kind = "online" if b.distribution != "tv" else "tv"
        channel = _channel_name(b.channel)
        key = (kind, channel)
        if key in seen:
            continue
        seen.add(key)
        suffix = "" if b.tv_start == main_start else f" od {b.tv_start:%H:%M}"
        by_type[kind].append(f"{html.escape(channel)}{suffix}")
    lines = []
    if by_type["tv"]:
        lines.append("📺 " + " • ".join(by_type["tv"]))
    if by_type["online"]:
        lines.append("💻 " + " • ".join(by_type["online"]))
    return lines


def format_digest(items: list[DigestItem], *, day: date) -> str | None:
    if not items:
        return None

    lines = ["📺 <b>SPORT V TV</b>", html.escape(_format_date(day)), ""]
    current_sport: str | None = None
    current_comp: str | None = None

    labels = {
        "hockey": "🏒 <b>HOKEJ</b>",
        "biathlon": "🎯 <b>BIATLON</b>",
        "athletics": "🏃 <b>ATLETIKA</b>",
    }

    for item in items:
        if item.sport != current_sport:
            if lines[-1] != "":
                lines.append("")
            lines.append(labels.get(item.sport, f"<b>{html.escape(item.sport.upper())}</b>"))
            current_sport = item.sport
            current_comp = None

        if item.competition and item.competition != current_comp:
            lines.append(html.escape(item.competition))
            current_comp = item.competition

        if item.sport == "biathlon" and item.location:
            place = item.location
            if item.country:
                place += f" ({item.country})"
            lines.append(html.escape(place))

        lines.append("")
        lines.append(f"<b>{item.start:%H:%M}</b>  {html.escape(item.title)}")
        lines.extend(_media_lines(item.broadcasts, item.start))

    return "\n".join(lines).strip()


def build_today_digest(
    db_path: str | Path = "data/sports_events.db",
    *,
    now: datetime | None = None,
) -> str | None:
    now_local = (now or datetime.now(PRAGUE)).astimezone(PRAGUE)
    items = collect_today_items(db_path, now=now_local)
    return format_digest(items, day=now_local.date())
