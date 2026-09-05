from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import quote_plus, urljoin, urlparse
from zoneinfo import ZoneInfo

import yaml
from bs4 import BeautifulSoup, Tag
from playwright.sync_api import Browser, BrowserContext, Playwright, sync_playwright

from models.tv_program import TVProgram


BASE_URL = "https://tvprogram.idnes.cz/"
SEARCH_URL = BASE_URL + "hledani?slovo={query}"
DETAIL_ID_RE = re.compile(r"\.id(?P<id>\d+)(?:$|[?#])")
DETAIL_PATH_RE = re.compile(
    r"^/(?P<channel>[^/]+)/(?P<dow>po|ut|st|ct|pa|so|ne)-(?P<hour>\d{1,2})\.(?P<minute>\d{2})-",
    re.IGNORECASE,
)
TIME_RANGE_RE = re.compile(r"(?P<sh>\d{1,2}):(?P<sm>\d{2})\s*-\s*(?P<eh>\d{1,2}):(?P<em>\d{2})")
DATE_RE = re.compile(
    r"(?:Pondělí|Úterý|Středa|Čtvrtek|Pátek|Sobota|Neděle)\s+(?P<day>\d{1,2})\.(?P<month>\d{1,2})\.",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedSchedule:
    source_id: str
    channel_slug: str
    title: str
    description: Optional[str]
    start_local: datetime
    end_local: datetime
    source_url: str


class IdnesTVScraper:
    source = "idnes"

    def __init__(
        self,
        config_path: str = "config/tv_channels.yaml",
        now: Optional[datetime] = None,
        timeout: int = 30,
    ):
        config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))["idnes"]
        self.tz_name = config.get("timezone", "Europe/Prague")
        self.tz = ZoneInfo(self.tz_name)
        self.channels: dict[str, str] = config["channels"]
        self.search_queries: list[str] = config.get("search_queries", [])
        self.max_pages_per_query = int(config.get("max_pages_per_query", 5))
        self.timeout = timeout
        self.now = now.astimezone(self.tz) if now else datetime.now(self.tz)
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    def _ensure_browser(self) -> BrowserContext:
        if self._context is not None:
            return self._context
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context(
            locale="cs-CZ",
            timezone_id=self.tz_name,
            viewport={"width": 1280, "height": 900},
        )
        return self._context

    def _close_browser(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def _fetch_html(self, url: str) -> str:
        context = self._ensure_browser()
        page = context.new_page()
        try:
            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.timeout * 1000,
            )
            if response is not None and response.status >= 400:
                raise RuntimeError(f"iDNES HTTP {response.status} for {url}")

            # Discovery proved that programme links are present in the rendered DOM.
            # Do not require them here: a genuinely empty search page is still valid and
            # is diagnosed by _scrape_query below.
            try:
                page.wait_for_selector('a[href*=".id"]', timeout=min(self.timeout, 10) * 1000)
            except Exception:
                pass
            return page.content()
        finally:
            page.close()

    @staticmethod
    def _normalize_text(value: str) -> str:
        value = unicodedata.normalize("NFKD", value.casefold())
        value = "".join(ch for ch in value if not unicodedata.combining(ch))
        value = re.sub(r"[^a-z0-9]+", " ", value)
        return " ".join(value.split())

    @classmethod
    def _is_query_relevant(cls, query: str, title: str) -> bool:
        q = cls._normalize_text(query)
        t = cls._normalize_text(title)

        aliases = {
            "atletika": (
                "atletika", "athletics", "diamantova liga",
                "world athletics", "mcr v atletice",
            ),
            "biatlon": ("biatlon", "biathlon"),
            "hokej": (
                "hokej", "ice hockey", "elh", "extraliga",
                "maxa liga", "tipsport extraliga", "nhl",
                "buly", "studio hokej",
            ),
        }
        terms = aliases.get(q, (q,))
        return any(cls._normalize_text(term) in t for term in terms)

    @staticmethod
    def _source_id(url: str) -> Optional[str]:
        match = DETAIL_ID_RE.search(url)
        return match.group("id") if match else None

    @staticmethod
    def _detail_parts(url: str) -> Optional[dict[str, str]]:
        return DETAIL_PATH_RE.match(urlparse(url).path).groupdict() if DETAIL_PATH_RE.match(urlparse(url).path) else None

    def _resolve_date(self, day: int, month: int) -> date:
        """Resolve iDNES day/month to the nearest plausible date in its ~14-day horizon."""
        candidates = []
        for year in (self.now.year - 1, self.now.year, self.now.year + 1):
            try:
                candidates.append(date(year, month, day))
            except ValueError:
                continue
        if not candidates:
            raise ValueError(f"Invalid iDNES date {day}.{month}.")

        today = self.now.date()
        # Search pages can briefly retain same-day/past entries; allow a small past window.
        plausible = [d for d in candidates if today - timedelta(days=2) <= d <= today + timedelta(days=31)]
        if plausible:
            return min(plausible, key=lambda d: abs((d - today).days))
        return min(candidates, key=lambda d: abs((d - today).days))

    @staticmethod
    def _schedule_metadata_before(anchor: Tag) -> tuple[Optional[re.Match[str]], Optional[re.Match[str]]]:
        """Find the nearest time range and date rendered immediately before a result title.

        iDNES search results are laid out in document order as:
        ``time range -> date -> title link -> metadata``.  The time/date are siblings
        (or cousins), not descendants of the title link's smallest container, so an
        ancestor-only lookup silently drops every result.
        """
        time_match = None
        date_match = None
        inspected = 0
        for node in anchor.previous_elements:
            if inspected >= 40 or (time_match is not None and date_match is not None):
                break
            if isinstance(node, str):
                text = " ".join(node.split())
                if not text:
                    continue
                inspected += 1
                if date_match is None:
                    date_match = DATE_RE.search(text)
                if time_match is None:
                    time_match = TIME_RANGE_RE.search(text)
        return time_match, date_match

    @staticmethod
    def _description(container: Tag, title: str) -> Optional[str]:
        parts = [s.strip() for s in container.stripped_strings if s.strip()]
        ignored = {title}
        kept = []
        for part in parts:
            if part in ignored or TIME_RANGE_RE.fullmatch(part) or DATE_RE.fullmatch(part):
                continue
            if DATE_RE.search(part) or TIME_RANGE_RE.search(part):
                # Usually a combined header; it is schedule metadata, not description.
                continue
            kept.append(part)
        if not kept:
            return None
        # Avoid huge text when an ancestor was broader than expected.
        description = " ".join(kept)
        return description[:1000] if description else None

    @staticmethod
    def _detail_link_count(html: str, page_url: str = BASE_URL) -> int:
        soup = BeautifulSoup(html, "html.parser")
        count = 0
        for anchor in soup.find_all("a", href=True):
            href = urljoin(page_url, anchor["href"])
            if IdnesTVScraper._source_id(href) and IdnesTVScraper._detail_parts(href):
                count += 1
        return count

    def parse_search_html(self, html: str, page_url: str = BASE_URL) -> list[ParsedSchedule]:
        soup = BeautifulSoup(html, "html.parser")
        parsed: list[ParsedSchedule] = []
        seen: set[tuple[str, datetime, str]] = set()

        for anchor in soup.find_all("a", href=True):
            href = urljoin(page_url, anchor["href"])
            source_id = self._source_id(href)
            parts = self._detail_parts(href)
            if not source_id or not parts:
                continue

            channel_slug = parts["channel"].lower()
            if channel_slug not in self.channels:
                continue

            title = " ".join(anchor.stripped_strings).strip()
            if not title:
                continue

            time_match, date_match = self._schedule_metadata_before(anchor)
            if not time_match or not date_match:
                continue

            local_date = self._resolve_date(int(date_match.group("day")), int(date_match.group("month")))
            start_t = time(int(time_match.group("sh")), int(time_match.group("sm")))
            end_t = time(int(time_match.group("eh")), int(time_match.group("em")))
            start_local = datetime.combine(local_date, start_t, self.tz)
            end_local = datetime.combine(local_date, end_t, self.tz)
            if end_local <= start_local:
                end_local += timedelta(days=1)

            # URL itself contains the advertised start time. A mismatch means we likely
            # climbed into a container belonging to a neighboring programme entry.
            url_start = (int(parts["hour"]), int(parts["minute"]))
            if (start_local.hour, start_local.minute) != url_start:
                continue

            key = (source_id, start_local, channel_slug)
            if key in seen:
                continue
            seen.add(key)
            parsed.append(
                ParsedSchedule(
                    source_id=source_id,
                    channel_slug=channel_slug,
                    title=title,
                    description=None,
                    start_local=start_local,
                    end_local=end_local,
                    source_url=href,
                )
            )
        return parsed

    @staticmethod
    def _next_page_url(html: str, current_url: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        for anchor in soup.find_all("a", href=True):
            label = " ".join(anchor.stripped_strings).strip().casefold()
            if label in {"další", "dalsi", "next"}:
                return urljoin(current_url, anchor["href"])
        return None

    def _scrape_query(self, query: str) -> Iterable[ParsedSchedule]:
        url: Optional[str] = SEARCH_URL.format(query=quote_plus(query))
        visited: set[str] = set()
        for _ in range(self.max_pages_per_query):
            if not url or url in visited:
                break
            visited.add(url)
            html = self._fetch_html(url)
            detail_links = self._detail_link_count(html, url)
            parsed = self.parse_search_html(html, url)
            print(
                f"[IDNES] query={query!r} page={url} html={len(html)} "
                f"detail_links={detail_links} parsed={len(parsed)}"
            )
            if detail_links == 0:
                soup = BeautifulSoup(html, "html.parser")
                title = soup.title
                title_text = title.get_text(" ", strip=True) if title else "<no-title>"
                body_text = " ".join(soup.stripped_strings)

                # A valid iDNES search page can legitimately contain zero results
                # (for example when a sport has no broadcasts in the current
                # programme horizon).  The earlier HTTP fallback failure instead
                # returned the generic iDNES homepage, whose title did not identify
                # the TV-program search page.
                is_tv_search_page = (
                    "tv program idnes.cz" in title_text.casefold()
                    and (
                        "výsledky vyhledávání" in body_text.casefold()
                        or "/hledani" in url
                    )
                )
                if is_tv_search_page:
                    print(f"[IDNES] query={query!r} no scheduled programmes -> OK")
                    break

                raise RuntimeError(
                    "iDNES returned HTML without programme detail links "
                    f"for query {query!r}; title={title_text!r}, html_len={len(html)}"
                )
            relevant = [item for item in parsed if self._is_query_relevant(query, item.title)]
            filtered = len(parsed) - len(relevant)
            if filtered:
                print(
                    f"[IDNES] query={query!r} filtered_irrelevant={filtered} "
                    f"kept={len(relevant)}"
                )
            yield from relevant
            url = self._next_page_url(html, url)

    def scrape(self) -> list[TVProgram]:
        discovered_at = datetime.now(timezone.utc)
        programs: list[TVProgram] = []
        seen_ids: set[tuple[str, datetime, str]] = set()
        seen_broadcasts: set[tuple[str, str, datetime]] = set()

        try:
            for query in self.search_queries:
                for item in self._scrape_query(query):
                    channel = self.channels[item.channel_slug]
                    start_utc = item.start_local.astimezone(timezone.utc)
                    end_utc = item.end_local.astimezone(timezone.utc)
                    id_key = (item.source_id, start_utc, channel)
                    broadcast_key = (
                        channel,
                        self._normalize_text(item.title),
                        start_utc,
                    )
                    if id_key in seen_ids or broadcast_key in seen_broadcasts:
                        continue
                    seen_ids.add(id_key)
                    seen_broadcasts.add(broadcast_key)
                    programs.append(
                        TVProgram(
                            source=self.source,
                            source_id=item.source_id,
                            channel=channel,
                            title=item.title,
                            description=item.description,
                            start_datetime=start_utc,
                            end_datetime=end_utc,
                            source_url=item.source_url,
                            discovered_at=discovered_at,
                            timezone=self.tz_name,
                            distribution="tv",
                        )
                    )
        finally:
            self._close_browser()

        programs.sort(key=lambda p: (p.start_datetime, p.channel, p.title))
        return programs
