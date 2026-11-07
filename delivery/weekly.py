from __future__ import annotations

import html
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from pathlib import Path

from delivery.digest import (
    PRAGUE,
    UTC,
    _competition_cs,
    _country_cs,
    _dedupe_broadcasts,
    _format_date,
    _location_cs,
    _media_lines,
    _norm,
    _parse_dt,
    Broadcast,
    collect_idnes_items,
    youtube_broadcasts,
)

SPORT_LABELS = {
    "hockey": "🏒 HOKEJ",
    "biathlon": "🎯 BIATLON",
    "athletics": "🏃 ATLETIKA",
}
SPORT_PRIORITY = {"hockey": 0, "biathlon": 1, "athletics": 2}


@dataclass(frozen=True)
class WeeklyEvent:
    event_id: int
    sport: str
    competition: str
    name: str
    start: datetime
    location: str | None
    country: str | None
    broadcasts: tuple[Broadcast, ...] = ()


def next_week_range(*, now: datetime | None = None) -> tuple[date, date]:
    local_now = (now or datetime.now(PRAGUE)).astimezone(PRAGUE)
    days_until_monday = 7 - local_now.weekday()
    monday = local_now.date() + timedelta(days=days_until_monday)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _competition_name(row: sqlite3.Row, sport: str) -> str:
    proxy = Broadcast(
        event_id=int(row["id"]),
        sport=sport,
        competition=row["competition"] or "",
        event_name=row["name"] or "",
        location=row["location"],
        country=row["country"],
        source_url=row["source_url"] or "",
        tv_start=datetime.now(PRAGUE),
        tv_end=None,
        channel="",
        distribution="tv",
        tv_title="",
    )
    return _competition_cs(proxy)


def collect_next_week_events(
    db_path: str | Path = "data/sports_events.db", *, now: datetime | None = None,
) -> list[WeeklyEvent]:
    monday, sunday = next_week_range(now=now)
    start_local = datetime.combine(monday, time.min, tzinfo=PRAGUE)
    end_local = datetime.combine(sunday + timedelta(days=1), time.min, tzinfo=PRAGUE)
    start_utc = start_local.astimezone(UTC).isoformat()
    end_utc = end_local.astimezone(UTC).isoformat()

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT id, sport, competition, name, start_datetime, end_datetime,
                   location, country, source_url
            FROM sports_events
            WHERE source = 'atletika_cz' AND start_datetime >= ? AND start_datetime < ?
            ORDER BY start_datetime, id
            """,
            (start_utc, end_utc),
        ).fetchall()
    finally:
        con.close()

    tv_by_event: dict[int, list[Broadcast]] = defaultdict(list)
    for broadcast in youtube_broadcasts(db_path, monday, sunday + timedelta(days=1)):
        tv_by_event[broadcast.event_id].append(broadcast)
    events: list[WeeklyEvent] = []
    athletics_groups: dict[tuple[date, str, str], list[tuple[sqlite3.Row, datetime, str, str | None, str | None]]] = defaultdict(list)

    for row in rows:
        start = _parse_dt(row["start_datetime"])
        if start is None:
            continue
        local_start = start.astimezone(PRAGUE)
        competition = _competition_name(row, "athletics")
        location = _location_cs(row["location"])
        country = _country_cs(row["country"])
        key = (local_start.date(), _norm(competition), _norm(location or row["name"] or ""))
        athletics_groups[key].append((row, local_start, competition, location, country))

    for group in athletics_groups.values():
        group.sort(key=lambda item: item[1])
        first_row, first_start, competition, location, country = group[0]
        all_broadcasts: list[Broadcast] = []
        for row, _, _, _, _ in group:
            all_broadcasts.extend(tv_by_event.get(int(row["id"]), ()))
        broadcasts = _dedupe_broadcasts(all_broadcasts) if all_broadcasts else ()
        if location and country:
            name = f"{location} ({country})"
        else:
            name = location or first_row["name"] or "Atletika"
        events.append(
            WeeklyEvent(
                event_id=int(first_row["id"]),
                sport="athletics",
                competition=competition,
                name=name,
                start=first_start,
                location=location,
                country=country,
                broadcasts=broadcasts,
            )
        )

    for item in collect_idnes_items(db_path, monday, sunday + timedelta(days=1)):
        if item.sport == "athletics" and item.competition in {"Mistrovství ČR", "Halové mistrovství ČR"}:
            matches = [
                i for i, event in enumerate(events)
                if event.start.date() == item.start.date() and event.competition == item.competition
            ]
            if len(matches) == 1:
                index = matches[0]
                event = events[index]
                events[index] = replace(event, broadcasts=_dedupe_broadcasts([
                    *event.broadcasts, *item.broadcasts,
                ]))
                continue
        events.append(WeeklyEvent(
            event_id=item.broadcasts[0].event_id, sport=item.sport, competition=item.competition,
            name=item.title, start=item.start, location=item.location, country=item.country,
            broadcasts=item.broadcasts,
        ))

    return sorted(events, key=lambda item: (item.start, SPORT_PRIORITY.get(item.sport, 99), item.name))


def format_weekly_report(
    events: list[WeeklyEvent], *, monday: date, sunday: date,
) -> str | None:
    if not events:
        return None

    by_day: dict[date, list[WeeklyEvent]] = defaultdict(list)
    for event in events:
        by_day[event.start.date()].append(event)

    lines = [f"{html.escape(_format_date(monday))} – {html.escape(_format_date(sunday))}"]
    for day in sorted(by_day):
        lines.append("")
        lines.append(f"<b>{html.escape(_format_date(day))}</b>")
        day_events = sorted(
            by_day[day],
            key=lambda item: (item.start, SPORT_PRIORITY.get(item.sport, 99), item.name),
        )
        current_sport: str | None = None
        current_competition: str | None = None
        for event in day_events:
            if event.sport != current_sport:
                lines.append("")
                lines.append(f"<b>{SPORT_LABELS.get(event.sport, event.sport.upper())}</b>")
                current_sport = event.sport
                current_competition = None
            if event.competition and event.competition != current_competition:
                lines.append(f"🏆 {html.escape(event.competition)}")
                current_competition = event.competition
            lines.append(f"<b>{event.start:%H:%M}</b>  {html.escape(event.name)}")
            if event.broadcasts:
                lines.extend(_media_lines(event.broadcasts, event.start))

    return "\n".join(lines).strip()


def build_next_week_report(
    db_path: str | Path = "data/sports_events.db", *, now: datetime | None = None,
) -> str | None:
    monday, sunday = next_week_range(now=now)
    events = collect_next_week_events(db_path, now=now)
    return format_weekly_report(events, monday=monday, sunday=sunday)