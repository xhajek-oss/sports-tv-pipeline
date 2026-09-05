import re
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from models.sports_event import SportsEvent
from .base import BaseScraper


TOURNAMENTS_URL = "https://www.iihf.com/en/tournamentslist"

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# IIHF season 2027 tournaments can start already in late 2026.
SEASONS = (2027,)

COUNTRY_TIMEZONES = {
    "GERMANY": "Europe/Berlin",
    "ESTONIA": "Europe/Tallinn",
    "UA EMIRATES": "Asia/Dubai",
    "UNITED ARAB EMIRATES": "Asia/Dubai",
    "KYRGYZSTAN": "Asia/Bishkek",
    "CHINESE TAIPEI": "Asia/Taipei",
    "TAIWAN": "Asia/Taipei",
    "KUWAIT": "Asia/Kuwait",
    "MALAYSIA": "Asia/Kuala_Lumpur",
    "CANADA": "America/Toronto",
    "UNITED STATES": "America/New_York",
    "USA": "America/New_York",
    "SLOVENIA": "Europe/Ljubljana",
    "LITHUANIA": "Europe/Vilnius",
    "CROATIA": "Europe/Zagreb",
    "SERBIA": "Europe/Belgrade",
    "BULGARIA": "Europe/Sofia",
    "SOUTH AFRICA": "Africa/Johannesburg",
    "ITALY": "Europe/Rome",
    "KOREA": "Asia/Seoul",
    "TÜRKIYE": "Europe/Istanbul",
    "TURKIYE": "Europe/Istanbul",
    "SWITZERLAND": "Europe/Zurich",
    "CZECHIA": "Europe/Prague",
    "CZECH REPUBLIC": "Europe/Prague",
    "SLOVAKIA": "Europe/Bratislava",
    "AUSTRIA": "Europe/Vienna",
    "SWEDEN": "Europe/Stockholm",
    "FINLAND": "Europe/Helsinki",
    "NORWAY": "Europe/Oslo",
    "DENMARK": "Europe/Copenhagen",
    "HUNGARY": "Europe/Budapest",
    "LATVIA": "Europe/Riga",
}

GAME_RE = re.compile(
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r".{0,220}?"
    r"(?P<home>[A-Z]{3})\s+vs\s+(?P<away>[A-Z]{3})"
    r".{0,180}?"
    r"(?P<venue>[A-Za-z0-9À-ž .'/()-]+?)\s+"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})",
    re.IGNORECASE | re.DOTALL,
)


def _norm(text: str) -> str:
    return " ".join(text.split())


def _timezone_for_country(country: str) -> str:
    upper = _norm(country).upper()
    for marker, tz_name in COUNTRY_TIMEZONES.items():
        if marker in upper:
            return tz_name
    raise RuntimeError(
        f"Unknown IIHF tournament timezone for country {country!r}. "
        "Add it to COUNTRY_TIMEZONES before storing event times."
    )


def _parse_schedule(
    text: str,
    year: int,
    competition: str,
    country: str,
    source_url: str,
) -> list[SportsEvent]:
    text = _norm(text)
    tz_name = _timezone_for_country(country)
    local_tz = ZoneInfo(tz_name)
    discovered_at = datetime.now(timezone.utc)

    events = []
    seen = set()

    for m in GAME_RE.finditer(text):
        home = m.group("home").upper()
        away = m.group("away").upper()
        venue = _norm(m.group("venue"))

        # Prevent status text from becoming part of venue.
        for marker in ("Game Centre ", "highlights ", "UPCOMING ", "FINAL "):
            venue = venue.replace(marker, "")
        venue = venue.strip()

        local_dt = datetime(
            year,
            MONTHS[m.group("month").title()],
            int(m.group("day")),
            int(m.group("hour")),
            int(m.group("minute")),
            tzinfo=local_tz,
        )
        utc_dt = local_dt.astimezone(timezone.utc)

        key = (utc_dt, home, away)
        if key in seen:
            continue
        seen.add(key)

        events.append(
            SportsEvent(
                source="iihf",
                source_id=f"{year}-{local_dt:%m%d%H%M}-{home}-{away}",
                sport="ice_hockey",
                competition=competition,
                name=f"{home} - {away}",
                start_datetime=utc_dt,
                end_datetime=None,
                location=venue or None,
                country=country,
                source_url=source_url,
                discovered_at=discovered_at,
                timezone=tz_name,
            )
        )

    return events


class IIHFScraper(BaseScraper):
    source = "iihf"

    def scrape(self) -> Iterable[SportsEvent]:
        all_events = []
        seen = set()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(locale="en-US")

            try:
                for season in SEASONS:
                    url = f"{TOURNAMENTS_URL}?selectedSeason={season}"
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(2000)

                    links = page.locator(f'a[href*="/en/events/{season}/"]').evaluate_all(
                        "(els) => els.map(el => ({href: el.href, text: el.innerText}))"
                    )

                    tournament_urls = []
                    seen_urls = set()
                    for item in links:
                        href = item["href"].split("#")[0].rstrip("/")
                        # Strip child pages such as /news; keep tournament root.
                        match = re.search(
                            rf"(https://www\.iihf\.com/en/events/{season}/[^/?#]+)",
                            href,
                            re.IGNORECASE,
                        )
                        if not match:
                            continue
                        root = match.group(1)
                        if root not in seen_urls:
                            seen_urls.add(root)
                            tournament_urls.append(root)

                    for root in tournament_urls:
                        schedule_url = root + "/schedule"
                        page.goto(
                            schedule_url,
                            wait_until="domcontentloaded",
                            timeout=60000,
                        )
                        page.wait_for_timeout(750)

                        body = _norm(page.locator("body").inner_text())

                        # Skip tournaments whose schedule is not published yet.
                        if "No results found" in body or "TBA" == body.strip():
                            continue

                        title = _norm(page.locator("h1").first.inner_text()) if page.locator("h1").count() else f"IIHF {season}"

                        # Tournament pages generally expose country in their header.
                        # Search page text for a known country marker.
                        country = None
                        upper = body.upper()
                        for marker in COUNTRY_TIMEZONES:
                            if marker in upper:
                                country = marker
                                break
                        if not country:
                            # Better to skip than silently store a wrong timezone.
                            continue

                        for event in _parse_schedule(
                            body, season, title, country, page.url
                        ):
                            key = (event.start_datetime, event.name, event.competition)
                            if key in seen:
                                continue
                            seen.add(key)
                            all_events.append(event)
            finally:
                browser.close()

        # A future IIHF tournament can already be listed while the individual
        # game schedule is not published yet. That is a valid state, not an error.
        # The scraper will start returning games automatically once IIHF exposes
        # concrete schedule rows.
        all_events.sort(key=lambda event: event.start_datetime)
        return all_events
