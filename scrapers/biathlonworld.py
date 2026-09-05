import re
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urljoin, urlparse, parse_qs
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from models.sports_event import SportsEvent
from .base import BaseScraper


SOURCE_URL = "https://www.biathlonworld.com/calendar"

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# Known IBU venues. Add a venue here if a future calendar introduces a new one.
VENUE_TIMEZONES = {
    "munich": "Europe/Berlin",
    "münchen": "Europe/Berlin",
    "idre fjaell": "Europe/Stockholm",
    "idre fjäll": "Europe/Stockholm",
    "ostersund": "Europe/Stockholm",
    "östersund": "Europe/Stockholm",
    "oestersund": "Europe/Stockholm",
    "torsby": "Europe/Stockholm",
    "hochfilzen": "Europe/Vienna",
    "obertilliach": "Europe/Vienna",
    "annecy": "Europe/Paris",
    "le grand bornand": "Europe/Paris",
    "oberhof": "Europe/Berlin",
    "ruhpolding": "Europe/Berlin",
    "arber": "Europe/Berlin",
    "nove mesto": "Europe/Prague",
    "nové město": "Europe/Prague",
    "pokljuka": "Europe/Ljubljana",
    "oslo": "Europe/Oslo",
    "holmenkollen": "Europe/Oslo",
    "sjusjoen": "Europe/Oslo",
    "sjusjøen": "Europe/Oslo",
    "kontiolahti": "Europe/Helsinki",
    "vuokatti": "Europe/Helsinki",
    "lenzerheide": "Europe/Zurich",
    "goms": "Europe/Zurich",
    "antholz": "Europe/Rome",
    "anterselva": "Europe/Rome",
    "martell": "Europe/Rome",
    "val martello": "Europe/Rome",
    "ridnaun": "Europe/Rome",
    "val ridanna": "Europe/Rome",
    "madona": "Europe/Riga",
    "otepaa": "Europe/Tallinn",
    "otepää": "Europe/Tallinn",
    "brasov": "Europe/Bucharest",
    "brașov": "Europe/Bucharest",
    "szklarska poreba": "Europe/Warsaw",
    "jakuszyce": "Europe/Warsaw",
    "brezno": "Europe/Bratislava",
    "osrblie": "Europe/Bratislava",
    "canmore": "America/Edmonton",
    "soldier hollow": "America/Denver",
    "salt lake": "America/Denver",
}

COMPETITION_RE = re.compile(
    r"\b(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"\s*(?P<day>\d{1,2})\s*(?P<year>\d{4})"
    r"\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?"
    r"\s*(?P<hour>\d{1,2}):(?P<minute>\d{2})"
    r"\s*(?P<name>.+?)"
    r"\s*(?:Scheduled|Finished|Live)\b",
    re.IGNORECASE | re.DOTALL,
)


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _event_id_from_url(url: str) -> str | None:
    values = parse_qs(urlparse(url).query).get("EventId")
    return values[0].strip() if values and values[0].strip() else None


def _timezone_for_location(location: str | None) -> str:
    value = (location or "").lower()
    for marker, tz_name in VENUE_TIMEZONES.items():
        if marker in value:
            return tz_name
    raise RuntimeError(
        f"Unknown Biathlon World venue timezone: {location!r}. "
        "Add it to VENUE_TIMEZONES before storing event times."
    )


def _parse_competitions(
    text: str,
    location: str | None,
    country: str | None,
    source_url: str,
    competition: str = "International Biathlon Union",
) -> list[SportsEvent]:
    compact = _normalize_text(text)
    discovered_at = datetime.now(timezone.utc)
    tz_name = _timezone_for_location(location)
    local_tz = ZoneInfo(tz_name)

    events = []
    seen = set()

    for match in COMPETITION_RE.finditer(compact):
        name = _normalize_text(match.group("name"))
        for marker in ("Upcoming competitions ", "Previous competitions ", "Competitions "):
            if marker in name:
                name = name.split(marker)[-1].strip()

        local_dt = datetime(
            int(match.group("year")),
            MONTHS[match.group("month").title()],
            int(match.group("day")),
            int(match.group("hour")),
            int(match.group("minute")),
            tzinfo=local_tz,
        )
        utc_dt = local_dt.astimezone(timezone.utc)

        source_id = (
            f"{_event_id_from_url(source_url) or 'event'}-"
            f"{local_dt:%Y%m%d%H%M}-"
            f"{re.sub(r'[^A-Za-z0-9]+', '-', name).strip('-').lower()}"
        )

        key = (utc_dt, name, source_url)
        if key in seen:
            continue
        seen.add(key)

        events.append(
            SportsEvent(
                source="biathlonworld",
                source_id=source_id,
                sport="biathlon",
                competition=competition,
                name=name,
                start_datetime=utc_dt,
                end_datetime=None,
                location=location,
                country=country,
                source_url=source_url,
                discovered_at=discovered_at,
                timezone=tz_name,
            )
        )

    return events


class BiathlonWorldScraper(BaseScraper):
    source = "biathlonworld"

    def scrape(self) -> Iterable[SportsEvent]:
        all_events = []
        seen_events = set()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="en-US")
            page = context.new_page()

            try:
                page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2500)

                hrefs = page.locator('a[href*="EventId="]').evaluate_all(
                    "(els) => els.map(el => el.href)"
                )

                event_urls = []
                seen_urls = set()
                for href in hrefs:
                    if not _event_id_from_url(href):
                        continue
                    absolute = urljoin(SOURCE_URL, href)
                    if absolute not in seen_urls:
                        seen_urls.add(absolute)
                        event_urls.append(absolute)

                if not event_urls:
                    event_urls = [page.url]

                for event_url in event_urls:
                    page.goto(event_url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(1000)

                    text = page.locator("body").inner_text()
                    h1 = page.locator("h1")
                    h2 = page.locator("h2")

                    location = _normalize_text(h1.first.inner_text()) if h1.count() else None
                    country = _normalize_text(h2.first.inner_text()) if h2.count() else None

                    for event in _parse_competitions(text, location, country, page.url):
                        key = (event.start_datetime, event.name, event.location)
                        if key in seen_events:
                            continue
                        seen_events.add(key)
                        all_events.append(event)
            finally:
                context.close()
                browser.close()

        # A season/event page may legitimately contain no published races yet.
        # Actual browser/network/parser errors still propagate as real errors.
        all_events.sort(key=lambda event: event.start_datetime)
        return all_events
