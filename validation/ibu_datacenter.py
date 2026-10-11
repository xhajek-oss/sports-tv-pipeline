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
