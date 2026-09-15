from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from models.sports_event import SportsEvent
from scrapers.base import BaseScraper


class CzechAthleticsScraper(BaseScraper):
    """Selected senior Czech championships from the Czech Athletics Federation."""

    source = "atletika_cz"
    TIMEZONE = ZoneInfo("Europe/Prague")
    TARGETS = (
        {
            "kind": "mcr_outdoor_senior",
            "competition": "MČR mužů a žen",
            "url": "https://www.atletika.cz/zpravodajstvi/vrcholne-akce/mcr-muzu-a-zen/",
        },
        {
            "kind": "mcr_indoor_senior",
            "competition": "HMČR mužů a žen",
            "url": "https://www.atletika.cz/zpravodajstvi/vrcholne-akce/hmcr-muzu-a-zen-2026/",
        },
    )

    META_RE = re.compile(
        r"(?P<d1>\d{1,2})\.\s*(?P<m1>\d{1,2})?\.?(?:\s*-\s*"
        r"(?P<d2>\d{1,2})\.\s*(?P<m2>\d{1,2})?\.?)?\s*"
        r"(?P<year>20\d{2})\s*,\s*(?P<location>[^\n]+)"
    )

    def scrape(self):
        events: list[SportsEvent] = []
        for target in self.TARGETS:
            response = requests.get(target["url"], timeout=30)
            response.raise_for_status()
            events.extend(self._parse_target(response.text, target))
        return events

    def _parse_target(self, html: str, target: dict[str, str]) -> list[SportsEvent]:
        text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
        match = self.META_RE.search(text)
        if not match:
            raise ValueError(f"Could not parse date/location for {target['kind']}")

        year = int(match.group("year"))
        d1 = int(match.group("d1"))
        d2 = int(match.group("d2") or d1)
        m2 = int(match.group("m2") or match.group("m1"))
        m1 = int(match.group("m1") or m2)
        start_date = date(year, m1, d1)
        end_date = date(year, m2, d2)
        location = match.group("location").strip()
        discovered_at = datetime.now(timezone.utc)

        result: list[SportsEvent] = []
        current = start_date
        day_number = 1
        while current <= end_date:
            local_start = datetime.combine(current, datetime.min.time(), tzinfo=self.TIMEZONE)
            result.append(
                SportsEvent(
                    source=self.source,
                    source_id=f"{target['kind']}:{current.isoformat()}",
                    sport="athletics",
                    competition=target["competition"],
                    name=f"{target['competition']} – {day_number}. den",
                    start_datetime=local_start.astimezone(timezone.utc),
                    end_datetime=None,
                    location=location,
                    country="CZE",
                    source_url=target["url"],
                    discovered_at=discovered_at,
                    timezone="Europe/Prague",
                )
            )
            current += timedelta(days=1)
            day_number += 1
        return result
