from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from models.tv_program import TVProgram
from scrapers.atletika_cz import CzechAthleticsScraper


class CzechAthleticsYouTubeScraper:
    """Discover official ČAS YouTube streams exclusively from Atletika.cz."""

    source = "czechathletics_youtube"

    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130 Safari/537.36",
            "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
        })

    @staticmethod
    def _is_atletika(url: str) -> bool:
        host = urlparse(url).netloc.casefold().split(":", 1)[0]
        return host == "atletika.cz" or host.endswith(".atletika.cz")

    def _fetch_atletika(self, url: str) -> requests.Response:
        """Fetch Atletika.cz only; never follow a redirect to another host."""
        if not self._is_atletika(url):
            raise ValueError(f"Refusing non-Atletika.cz request: {url}")

        current_url = url
        for _ in range(5):
            response = self.session.get(
                current_url,
                timeout=self.timeout,
                allow_redirects=False,
            )
            if not response.is_redirect and not response.is_permanent_redirect:
                response.raise_for_status()
                return response

            location = response.headers.get("Location")
            if not location:
                response.raise_for_status()
                return response
            target = urljoin(current_url, location)

            # A redirect target is data, not permission to fetch another site.
            if not self._is_atletika(target):
                response._atletika_external_redirect = target
                return response
            current_url = target

        raise requests.TooManyRedirects(f"Too many Atletika.cz redirects: {url}")

    @staticmethod
    def parse_atletika_stream_links(html: str, page_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        links: list[str] = []
        seen: set[str] = set()
        for anchor in soup.find_all("a", href=True):
            label = anchor.get_text(" ", strip=True).casefold()
            if "stream" not in label:
                continue
            href = urljoin(page_url, anchor["href"])
            if href not in seen:
                seen.add(href)
                links.append(href)
        return links

    @staticmethod
    def _is_youtube(url: str) -> bool:
        host = urlparse(url).netloc.casefold().split(":", 1)[0]
        return host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")

    @classmethod
    def resolve_youtube_from_atletika_html(cls, html: str, page_url: str) -> str | None:
        """Read a YouTube target embedded on an Atletika.cz page without requesting YouTube."""
        soup = BeautifulSoup(html, "html.parser")
        for tag, attr in (("a", "href"), ("iframe", "src")):
            for node in soup.find_all(tag):
                raw = node.get(attr)
                if not raw:
                    continue
                candidate = urljoin(page_url, raw)
                if cls._is_youtube(candidate):
                    return candidate
        return None

    def _resolve_stream_from_atletika(self, stream_url: str) -> str | None:
        if self._is_youtube(stream_url):
            return stream_url
        response = self._fetch_atletika(stream_url)
        external = getattr(response, "_atletika_external_redirect", None)
        if external:
            return external if self._is_youtube(external) else None
        return self.resolve_youtube_from_atletika_html(response.text, response.url)

    def scrape(self) -> list[TVProgram]:
        discovered_at = datetime.now(timezone.utc)
        index = self._fetch_atletika(CzechAthleticsScraper.INDEX_URL)
        targets = CzechAthleticsScraper.discover_targets(index.text, index.url)
        programs: list[TVProgram] = []
        seen_youtube: set[str] = set()
        event_parser = CzechAthleticsScraper()

        for target in targets:
            event_response = self._fetch_atletika(target["url"])
            events = event_parser._parse_target(event_response.text, target)
            stream_links = self.parse_atletika_stream_links(event_response.text, event_response.url)

            for day_index, stream_link in enumerate(stream_links):
                youtube_url = self._resolve_stream_from_atletika(stream_link)
                if not youtube_url or youtube_url in seen_youtube:
                    continue
                seen_youtube.add(youtube_url)

                # Atletika.cz is the authority for both event date and stream existence.
                # We intentionally never request YouTube. The all-day interval lets the
                # matcher associate the official stream with the corresponding event day
                # without inventing a broadcast start time.
                event = events[min(day_index, len(events) - 1)]
                start = event.start_datetime
                programs.append(TVProgram(
                    source=self.source,
                    source_id=youtube_url,
                    channel="YouTube",
                    title=event.name,
                    description=f"Oficiální ČAS stream: {target['competition']}",
                    start_datetime=start,
                    end_datetime=start + timedelta(days=1),
                    source_url=youtube_url,
                    discovered_at=discovered_at,
                    timezone="Europe/Prague",
                    distribution="online",
                ))

        programs.sort(key=lambda item: item.start_datetime)
        return programs
