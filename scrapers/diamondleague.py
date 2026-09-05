import json
import re
from datetime import date, datetime, time, timezone
from typing import Iterable
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from models.sports_event import SportsEvent
from .base import BaseScraper


SOURCE_URL = "https://www.diamondleague.com/calendar/"

MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}

VENUES = {
    "shanghai/keqiao": ("CHN", "Asia/Shanghai"),
    "shanghai": ("CHN", "Asia/Shanghai"),
    "xiamen": ("CHN", "Asia/Shanghai"),
    "rabat": ("MAR", "Africa/Casablanca"),
    "rome": ("ITA", "Europe/Rome"),
    "stockholm": ("SWE", "Europe/Stockholm"),
    "oslo": ("NOR", "Europe/Oslo"),
    "doha": ("QAT", "Asia/Qatar"),
    "paris": ("FRA", "Europe/Paris"),
    "eugene": ("USA", "America/Los_Angeles"),
    "monaco": ("MON", "Europe/Monaco"),
    "london": ("GBR", "Europe/London"),
    "lausanne": ("SUI", "Europe/Zurich"),
    "silesia": ("POL", "Europe/Warsaw"),
    "zurich": ("SUI", "Europe/Zurich"),
    "brussels": ("BEL", "Europe/Brussels"),
}

CALENDAR_RE = re.compile(
    r"(?P<day>\d{1,2})(?:-(?P<end_day>\d{1,2}))?\s+"
    r"(?P<month>January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+"
    r"(?P<city>Shanghai/Keqiao|Shanghai|Xiamen|Rabat|Rome|Stockholm|Oslo|"
    r"Doha|Paris|Eugene|Monaco|London|Lausanne|Silesia|Zurich|Brussels)"
    r"\s+\((?P<country>[A-Z]{3})\)",
    re.IGNORECASE,
)

TIME_ONLY_RE = re.compile(r"^(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

TIME_KEYS = {
    "start", "starttime", "startdatetime", "scheduled", "scheduledtime",
    "scheduledstart", "eventstart", "eventstarttime", "time", "datetime",
}
DATE_KEYS = {"date", "eventdate", "scheduleddate", "startdate"}
NAME_KEYS = {
    "discipline", "disciplinename", "event", "eventname", "name", "title",
    "description", "displayname", "longname", "shortname",
}


def _norm(text: str) -> str:
    return " ".join(text.split())


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _meeting_key(city: str) -> str:
    return city.strip().lower()


def _extract_calendar(text: str, year: int) -> list[dict]:
    compact = _norm(text)
    result = []
    seen = set()

    for m in CALENDAR_RE.finditer(compact):
        city = m.group("city")
        key = _meeting_key(city)
        venue = VENUES.get(key)
        if not venue:
            continue

        country, tz_name = venue
        start_day = int(m.group("day"))
        end_day = int(m.group("end_day") or start_day)
        item = {
            "year": year,
            "month": MONTHS[m.group("month").title()],
            "day": start_day,
            "end_day": end_day,
            "city": city,
            "country": country,
            "timezone": tz_name,
        }
        dedupe = (year, item["month"], start_day, end_day, key)
        if dedupe not in seen:
            seen.add(dedupe)
            result.append(item)

    return result


def _is_swiss_timing_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host.endswith("liveresults.swisstiming.com")


def _candidate_name(node: dict) -> str | None:
    preferred = []
    fallback = []
    for raw_key, value in node.items():
        if not isinstance(value, str):
            continue
        value = _norm(value)
        if not (2 <= len(value) <= 120):
            continue
        k = _key(str(raw_key))
        if k not in NAME_KEYS:
            continue
        if re.fullmatch(r"[\d:./ -]+", value):
            continue
        if any(token in value.lower() for token in ("cookie", "privacy", "select meeting")):
            continue
        if "discipline" in k or "event" in k:
            preferred.append(value)
        else:
            fallback.append(value)
    return (preferred or fallback or [None])[0]


def _parse_datetime_value(value: str, tz_name: str) -> datetime | None:
    value = value.strip()
    if not ISO_RE.match(value):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz_name))
    return dt


def _extract_node_datetime(node: dict, meeting: dict) -> datetime | None:
    tz_name = meeting["timezone"]
    date_value = None
    time_value = None

    for raw_key, value in node.items():
        if not isinstance(value, str):
            continue
        k = _key(str(raw_key))
        value = value.strip()

        if k in TIME_KEYS:
            dt = _parse_datetime_value(value, tz_name)
            if dt:
                return dt
            if TIME_ONLY_RE.match(value):
                time_value = value

        if k in DATE_KEYS and DATE_RE.match(value):
            date_value = value

    if not time_value:
        return None

    if date_value:
        try:
            d = date.fromisoformat(date_value)
        except ValueError:
            return None
    elif meeting["day"] == meeting["end_day"]:
        d = date(meeting["year"], meeting["month"], meeting["day"])
    else:
        # A time without a date is ambiguous for a multi-day meeting.
        return None

    parts = [int(x) for x in time_value.split(":")]
    while len(parts) < 3:
        parts.append(0)
    return datetime.combine(d, time(parts[0], parts[1], parts[2]), ZoneInfo(tz_name))


def _walk_schedule(payload, meeting: dict) -> list[tuple[str, datetime]]:
    found = []

    def walk(node):
        if isinstance(node, dict):
            name = _candidate_name(node)
            dt = _extract_node_datetime(node, meeting)
            if name and dt:
                found.append((name, dt))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return found



def _extract_swiss_timing_units(payload, meeting: dict) -> list[tuple[str, datetime, datetime | None]]:
    """Extract official Diamond League disciplines from Swiss Timing schedule JSON."""
    if not isinstance(payload, dict):
        return []

    units = payload.get("content", {}).get("full", {}).get("Units", {})
    if not isinstance(units, dict):
        return []

    result = []
    tz = ZoneInfo(meeting["timezone"])

    for unit in units.values():
        if not isinstance(unit, dict):
            continue

        stats = unit.get("Stats") or {}
        # The schedule also contains youth, promotional and para pre-programme
        # events. DiamondId marks the actual Diamond League disciplines.
        if not isinstance(stats, dict) or not stats.get("DiamondId"):
            continue

        name = _norm(str(unit.get("EventName") or unit.get("EventNameShort") or ""))
        start_ms = unit.get("StartTime")
        end_ms = unit.get("EndTime")
        date_text = str(unit.get("Date") or "")

        if not name or not isinstance(start_ms, (int, float)):
            continue

        try:
            start_utc = datetime.fromtimestamp(start_ms / 1000, timezone.utc)
        except (ValueError, OSError, OverflowError):
            continue

        # Swiss Timing StartTime/EndTime are Unix epoch milliseconds, i.e.
        # absolute UTC instants. Date is used as a sanity check in venue time.
        local_start = start_utc.astimezone(tz)
        if DATE_RE.match(date_text) and local_start.date().isoformat() != date_text:
            continue

        end_local = None
        if isinstance(end_ms, (int, float)):
            try:
                end_local = datetime.fromtimestamp(end_ms / 1000, timezone.utc).astimezone(tz)
            except (ValueError, OSError, OverflowError):
                end_local = None

        result.append((name, local_start, end_local))

    return result

def _make_event(meeting: dict, name: str, local_dt: datetime, source_url: str, end_local_dt: datetime | None = None) -> SportsEvent:
    if local_dt.tzinfo is None:
        local_dt = local_dt.replace(tzinfo=ZoneInfo(meeting["timezone"]))
    utc_dt = local_dt.astimezone(timezone.utc)
    city = meeting["city"]
    clean_name = _norm(name)
    source_id = (
        f"{utc_dt.strftime('%Y%m%dT%H%M%SZ')}-"
        f"{_meeting_key(city).replace('/', '-')}-"
        f"{re.sub(r'[^a-z0-9]+', '-', clean_name.lower()).strip('-')[:60]}"
    )

    return SportsEvent(
        source="diamondleague",
        source_id=source_id,
        sport="athletics",
        competition="Wanda Diamond League",
        name=f"{clean_name} - {city}",
        start_datetime=utc_dt,
        end_datetime=end_local_dt.astimezone(timezone.utc) if end_local_dt else None,
        location=city,
        country=meeting["country"],
        source_url=source_url,
        discovered_at=datetime.now(timezone.utc),
        timezone=meeting["timezone"],
    )


class DiamondLeagueScraper(BaseScraper):
    source = "diamondleague"

    def scrape(self) -> Iterable[SportsEvent]:
        events = []
        today_utc = datetime.now(timezone.utc).date()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="en-US")
            page = context.new_page()

            try:
                page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(800)
                body = page.locator("body").inner_text()

                year_match = re.search(r"Calendar\s+(20\d{2})", body, re.IGNORECASE)
                if not year_match:
                    return []

                year = int(year_match.group(1))
                meetings = _extract_calendar(body, year)

                # Only current/future meetings matter for TV matching. Keep a
                # one-day grace window so a meeting running across midnight is
                # not accidentally dropped.
                meetings = [
                    m for m in meetings
                    if date(m["year"], m["month"], m["end_day"]) >= today_utc
                ]

                links = page.locator("a").evaluate_all(
                    """els => els.map(a => ({
                        text: (a.innerText || '').trim(),
                        href: a.href
                    }))"""
                )
                city_urls = {}
                for item in links:
                    href = item.get("href") or ""
                    host = urlparse(href).netloc.lower()
                    text = (item.get("text") or "").lower()
                    if not host.endswith(".diamondleague.com"):
                        continue
                    for meeting in meetings:
                        city_key = _meeting_key(meeting["city"])
                        aliases = {city_key, city_key.split("/")[0]}
                        if any(alias in text for alias in aliases if alias):
                            city_urls.setdefault(city_key, f"https://{host}/")

                for meeting in meetings:
                    key = _meeting_key(meeting["city"])
                    base = city_urls.get(key)
                    if not base:
                        slug = key.split("/")[0].replace(" ", "")
                        base = f"https://{slug}.diamondleague.com/"
                    programme_url = base.rstrip("/") + "/en/programme-results/"

                    payloads = []
                    response_urls = []

                    def _is_dl_data_url(url):
                        lowered = url.lower()
                        return (
                            "swisstiming.com" in lowered
                            or "sportresult.com" in lowered
                            or "engine.io" in lowered
                            or "socket.io" in lowered
                        )

                    def on_response(response):
                        url = response.url
                        ctype = (response.headers.get("content-type") or "").lower()
                        if "json" not in ctype:
                            return
                        if not (
                            "swisstiming.com" in url.lower()
                            or "sportresult.com" in url.lower()
                        ):
                            return
                        try:
                            raw = response.body()
                            if len(raw) > 3_000_000:
                                return
                            payload = json.loads(raw.decode("utf-8"))
                        except Exception:
                            return

                        payloads.append(payload)
                        response_urls.append(url)

                    page.on("response", on_response)
                    try:
                        page.goto(programme_url, wait_until="domcontentloaded", timeout=45000)
                        page.wait_for_timeout(10000)

                        # If the embedded app has not requested its data yet,
                        # navigate directly to the Swiss Timing iframe once.
                        iframe_urls = page.locator("iframe").evaluate_all(
                            "els => els.map(e => e.src).filter(Boolean)"
                        )
                        swiss_urls = [u for u in iframe_urls if _is_swiss_timing_url(u)]
                        if swiss_urls and not payloads:
                            page.goto(swiss_urls[0], wait_until="domcontentloaded", timeout=45000)
                            page.wait_for_timeout(10000)
                    except Exception as exc:
                        print(f"diamondleague {meeting['city']}: load error: {exc}")
                    finally:
                        page.remove_listener("response", on_response)

                    parsed = []
                    for payload in payloads:
                        parsed.extend(_extract_swiss_timing_units(payload, meeting))

                    # Fallback for a future Swiss Timing schema that still exposes
                    # ordinary string date/time fields.
                    if not parsed:
                        for payload in payloads:
                            parsed.extend(
                                (name, local_dt, None)
                                for name, local_dt in _walk_schedule(payload, meeting)
                            )

                    seen = set()
                    for name, local_dt, end_local_dt in parsed:
                        # Restrict accidental matches to the meeting's own date span.
                        local_date = local_dt.astimezone(ZoneInfo(meeting["timezone"])).date()
                        first = date(meeting["year"], meeting["month"], meeting["day"])
                        last = date(meeting["year"], meeting["month"], meeting["end_day"])
                        if not (first <= local_date <= last):
                            continue
                        dedupe = (name.lower(), local_dt.isoformat())
                        if dedupe in seen:
                            continue
                        seen.add(dedupe)
                        events.append(_make_event(meeting, name, local_dt, programme_url, end_local_dt))

                    if not parsed:
                        print(
                            f"diamondleague {meeting['city']}: no schedule parsed "
                            f"from {len(payloads)} Swiss Timing JSON responses"
                        )
                        # Compact diagnostics: endpoint paths only, no payload dumps.
                        for url in response_urls[:5]:
                            print(f"  Swiss Timing JSON: {url}")

            finally:
                context.close()
                browser.close()

        events.sort(key=lambda event: event.start_datetime)
        return events
