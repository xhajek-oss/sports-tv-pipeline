import re
from urllib.request import Request, urlopen
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urljoin, urlparse, parse_qs
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from validation.ibu_datacenter import parse_official_competitions
from models.sports_event import SportsEvent
from .base import BaseScraper


SOURCE_URL = "https://www.biathlonworld.com/calendar"

SUMMER_EVENT_MARKERS = ("loop one", "summer", "roller", "rollerski", "roller ski")
SUMMER_EVENT_IDS = ("BT2627SWRLOG__",)


def _is_snow_biathlon_event(title: str, location: str | None, event_id: str | None) -> bool:
    if event_id and event_id.upper() in SUMMER_EVENT_IDS:
        return False
    label = f"{title} {location or ''}".lower()
    if any(marker in label for marker in SUMMER_EVENT_MARKERS):
        return False
    # SWRL is used by winter World Cup events too; never infer summer from this ID.
    return True


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


IBU_API_URL = "https://api.biathlonresults.com/modules/sportapi/api/Competitions?EventId="

# IBU RaceId discipline codes. Explicitly classify gender/age and event type.
# Unknown suffixes must fail closed rather than silently delete valid races.
RACE_CODES = {
    "SMIN": "Men's Individual", "SWIN": "Women's Individual",
    "SMSP": "Men's Sprint", "SWSP": "Women's Sprint",
    "SMPU": "Men's Pursuit", "SWPU": "Women's Pursuit",
    "SMMS": "Men's Mass Start", "SWMS": "Women's Mass Start",
    "SMRL": "Men's Relay", "SWRL": "Women's Relay",
    "MXRL": "Mixed Relay", "MXSR": "Single Mixed Relay",
    "SMSP2": "Men's Sprint 2", "SWSP2": "Women's Sprint 2",
    "SMM6": "Men's Mass Start 60", "SWM6": "Women's Mass Start 60",
    "SMSI": "Men's Short Individual", "SWSI": "Women's Short Individual",
}

AGE_GENDER = {
    "JM": "Junior Men", "JW": "Junior Women",
    "YM": "Youth Men", "YW": "Youth Women",
}
AGE_DISCIPLINES = {
    "IN": "Individual", "SI": "Short Individual", "SP": "Sprint",
    "SP2": "Sprint 2", "PU": "Pursuit", "MS": "Mass Start",
    "M6": "Mass Start 60", "RL": "Relay",
}


def _race_name(code: str) -> str | None:
    if code in RACE_CODES:
        return RACE_CODES[code]
    for prefix, category in AGE_GENDER.items():
        if code.startswith(prefix):
            discipline = AGE_DISCIPLINES.get(code[len(prefix):])
            return f"{category} {discipline}" if discipline else None
    return None


def _official_event_races(event_id: str, location: str, country: str | None,
                          source_url: str) -> list[SportsEvent]:
    """Fetch official IBU start times. Network/schema failures abort the scrape."""
    request = Request(IBU_API_URL + event_id, headers={
        "Accept": "application/json", "User-Agent": "sports-tv-pipeline/1.0",
    })
    with urlopen(request, timeout=25) as response:
        payload = response.read(2_000_001)
    if len(payload) > 2_000_000:
        raise RuntimeError(f"IBU API response too large for {event_id}")
    official = parse_official_competitions(payload.decode("utf-8-sig"))
    if not official:
        raise RuntimeError(f"IBU API returned no usable official races for {event_id}")
    discovered_at = datetime.now(timezone.utc)
    tz_name = _timezone_for_location(location)
    events = []
    for race_id, start in official.items():
        if not race_id.startswith(event_id):
            raise RuntimeError(f"IBU API race/event mismatch: {race_id} != {event_id}")
        code = race_id[len(event_id):]
        name = _race_name(code)
        if not name:
            raise RuntimeError(f"Unknown official IBU race code: {race_id}")
        events.append(SportsEvent(
            source="biathlonworld", source_id=race_id, sport="biathlon",
            competition="International Biathlon Union", name=name,
            start_datetime=start, end_datetime=None, location=location,
            country=country, source_url=source_url, discovered_at=discovered_at,
            timezone=tz_name,
        ))
    if not events:
        raise RuntimeError(f"No recognized IBU race codes for {event_id}")
    return events


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


def _event_dates_match_calendar_label(label: str, events: list[SportsEvent]) -> bool:
    """Reject stale race panels if their month/year differs from calendar entry."""
    match = re.search(r"(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(?P<year>20\d{2})", label, re.I)
    if not match:
        return False  # unknown date: fail closed
    month = MONTHS[match.group("month").title()]
    year = int(match.group("year"))
    return all(
        e.start_datetime.astimezone(ZoneInfo(e.timezone)).year == year
        and e.start_datetime.astimezone(ZoneInfo(e.timezone)).month == month
        and not (year == 2026 and month == 10)
        for e in events
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

                links = page.locator('a[href*="EventId="]').evaluate_all(
                    """(els) => els.map(el => ({
                        url: el.href,
                        label: [el.innerText, el.parentElement?.innerText,
                                el.parentElement?.parentElement?.innerText]
                            .filter(Boolean).join(" ").slice(0, 500)
                    }))"""
                )

                event_urls = []
                seen_urls = set()
                labels = {}
                for link in links:
                    href = link["url"]
                    if not _event_id_from_url(href):
                        continue
                    absolute = urljoin(SOURCE_URL, href)
                    if absolute not in seen_urls:
                        seen_urls.add(absolute)
                        event_urls.append(absolute)
                        labels[absolute] = link["label"]

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

                    # Reject non-snow events before persisting any races.
                    event_id = _event_id_from_url(page.url)
                    requested_id = _event_id_from_url(event_url)
                    if requested_id and requested_id != event_id:
                        raise RuntimeError(f"IBU event mismatch: requested {requested_id}, got {event_id}")
                    # Global navigation can mention summer races; only inspect event-specific labels.
                    calendar_label = labels.get(event_url, "")
                    if not _is_snow_biathlon_event(calendar_label, location, event_id):
                        continue
                    # PB identifies para-biathlon events. The IBU winter-race
                    # feed uses BT identifiers; PB is a separate discipline
                    # whose API schedule may legitimately be unpublished.
                    if requested_id and requested_id.startswith("PB"):
                        print(f"[BIATHLON] skipped para-biathlon event: {requested_id}")
                        continue
                    parsed = _parse_competitions(text, location, country, page.url)
                    # The IBU SPA may display the Munich Loop One panel under a
                    # winter EventId. Never accept that venue in the winter feed.
                    if (location or "").strip().lower() in ("munich", "münchen"):
                        print(f"[BIATHLON] skipped Munich/Loop One panel: {event_url}")
                        continue
                    # The IBU calendar sometimes renders the currently selected event
                    # even for a different EventId. Never associate those races with
                    # a different venue or silently store wrong times.
                    if parsed and requested_id and not all(
                        event.source_id.startswith(requested_id + "-") for event in parsed
                    ):
                        raise RuntimeError(f"IBU race/event mismatch: {requested_id}")
                    if parsed and not _event_dates_match_calendar_label(calendar_label, parsed):
                        print(f"[BIATHLON] skipped inconsistent calendar date: {event_url}")
                        continue
                    if not parsed:
                        continue
                    # HTML is only a guard against stale SPA panels. Official
                    # RaceId and UTC StartTime are the authoritative records.
                    official_events = _official_event_races(requested_id, location, country, page.url)
                    if not _event_dates_match_calendar_label(calendar_label, official_events):
                        print(f"[BIATHLON] skipped inconsistent official dates: {event_url}")
                        continue
                    for event in official_events:
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
