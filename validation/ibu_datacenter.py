"""Read-only parsing and comparison of IBU Datacenter competition schedules.

Official Sport API endpoint:
https://api.biathlonresults.com/modules/sportapi/api/Competitions?EventId=...
The documented StartTime field is an ISO-8601 UTC timestamp.
This module deliberately does not fetch or modify production records.
"""
from __future__ import annotations

from datetime import datetime, timezone
from xml.etree import ElementTree


def parse_official_competitions(xml_text: str) -> dict[str, datetime]:
    """Return official RaceId -> UTC start; ignore missing or malformed entries."""
    root = ElementTree.fromstring(xml_text)
    result: dict[str, datetime] = {}
    for element in root.iter():
        children = {child.tag.rsplit("}", 1)[-1]: (child.text or "").strip() for child in element}
        race_id = children.get("RaceId")
        start = children.get("StartTime")
        if not race_id or not start:
            continue
        try:
            parsed = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            continue  # UTC must be explicit
        result[race_id] = parsed.astimezone(timezone.utc)
    return result


def compare_official_start(scraped_start: datetime, official_start: datetime) -> bool:
    """True only for identical aware UTC instants, never naive datetimes."""
    if scraped_start.tzinfo is None or official_start.tzinfo is None:
        return False
    return scraped_start.astimezone(timezone.utc) == official_start.astimezone(timezone.utc)
