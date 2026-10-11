"""Read-only IBU Datacenter competition schedule validation.

The IBU Sport API can return JSON or XML depending on client/content negotiation.
Never assume that an unverified or timezone-naive timestamp is UTC.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from xml.etree import ElementTree


def _utc_start(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if result.tzinfo is None:
        return None
    return result.astimezone(timezone.utc)


def _xml_competitions(payload: str) -> dict[str, datetime]:
    root = ElementTree.fromstring(payload)
    result: dict[str, datetime] = {}
    for element in root.iter():
        children = {child.tag.rsplit("}", 1)[-1]: (child.text or "").strip() for child in element}
        race_id = children.get("RaceId")
        start = _utc_start(children.get("StartTime"))
        if race_id and start:
            result[race_id] = start
    return result


def _json_competitions(value: object) -> dict[str, datetime]:
    result: dict[str, datetime] = {}

    def visit(node: object) -> None:
        if isinstance(node, list):
            for child in node:
                visit(child)
        elif isinstance(node, dict):
            race_id = node.get("RaceId")
            start = _utc_start(node.get("StartTime"))
            if isinstance(race_id, str) and race_id.strip() and start:
                result[race_id.strip()] = start
            for child in node.values():
                if isinstance(child, (list, dict)):
                    visit(child)

    visit(value)
    return result


def parse_official_competitions(payload: str) -> dict[str, datetime]:
    """Parse UTC RaceId/StartTime pairs from IBU JSON or XML.

    Missing offsets, missing IDs and invalid timestamps are ignored. An invalid
    document raises ValueError or XML ParseError; callers must not treat it as
    an empty confirmed official schedule.
    """
    text = payload.lstrip("\ufeff \t\r\n")
    if text.startswith(("{", "[")):
        return _json_competitions(json.loads(text))
    return _xml_competitions(text)


def compare_official_start(scraped_start: datetime, official_start: datetime) -> bool:
    """True only for identical aware instants."""
    if scraped_start.tzinfo is None or official_start.tzinfo is None:
        return False
    return scraped_start.astimezone(timezone.utc) == official_start.astimezone(timezone.utc)


def audit_persisted_ibu_starts(db_path: str = "data/sports_events.db", sample_size: int = 3) -> int:
    """Independently re-fetch official starts for upcoming persisted senior races."""
    import sqlite3
    from urllib.request import Request, urlopen

    if sample_size < 1:
        raise ValueError("sample_size must be positive")
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT source_id, start_datetime FROM sports_events "
            "WHERE source = 'biathlonworld' AND source_id GLOB 'BT[0-9][0-9][0-9][0-9]S*' "
            "AND start_datetime >= ? ORDER BY start_datetime, source_id LIMIT ?",
            (datetime.now(timezone.utc).isoformat(), sample_size),
        ).fetchall()
    if not rows:
        raise RuntimeError("IBU audit: no upcoming senior races to verify")
    schedules: dict[str, dict[str, datetime]] = {}
    for race_id, stored_value in rows:
        if len(race_id) <= 14:
            raise RuntimeError(f"IBU audit: malformed race ID {race_id}")
        event_id = race_id[:14]
        if event_id not in schedules:
            url = "https://api.biathlonresults.com/modules/sportapi/api/Competitions?EventId=" + event_id
            request = Request(url, headers={"Accept": "application/json", "User-Agent": "sports-tv-pipeline/1.0"})
            with urlopen(request, timeout=25) as response:
                payload = response.read(2_000_001)
            if len(payload) > 2_000_000:
                raise RuntimeError(f"IBU audit: oversized response for {event_id}")
            schedules[event_id] = parse_official_competitions(payload.decode("utf-8-sig"))
        official = schedules[event_id].get(race_id)
        stored = datetime.fromisoformat(stored_value.replace("Z", "+00:00"))
        if official is None or not compare_official_start(stored, official):
            raise RuntimeError(f"IBU audit: official start mismatch for {race_id}: stored={stored_value} official={official}")
        print(f"[IBU AUDIT] verified {race_id}: {official.isoformat()}")
    return len(rows)
