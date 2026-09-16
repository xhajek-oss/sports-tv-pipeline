from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from models.tv_program import TVProgram
from scrapers.atletika_cz import CzechAthleticsScraper


PLAYER_RESPONSE_RE = re.compile(
    r"ytInitialPlayerResponse\s*=\s*({.+?})\s*;\s*</script>", re.DOTALL
)


class CzechAthleticsYouTubeScraper:
    """Use Atletika.cz as authority for ČAS streams, then read YouTube timing."""

    source = "czechathletics_youtube"

    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130 Safari/537.36",
            "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
        })

    def _fetch(self, url: str) -> requests.Response:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response

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

    def _resolve_youtube_url(self, stream_url: str) -> Optional[str]:
        response = self._fetch(stream_url)
        final_url = response.url
        host = urlparse(final_url).netloc.casefold()
        if host.endswith("youtube.com") or host.endswith("youtu.be"):
            return final_url

        soup = BeautifulSoup(response.text, "html.parser")
        candidates = []
        for tag in soup.find_all("a", href=True):
            candidates.append(tag.get("href"))
        for tag in soup.find_all("iframe", src=True):
            candidates.append(tag.get("src"))
        for raw in candidates:
            if not raw:
                continue
            candidate = urljoin(final_url, raw)
            candidate_host = urlparse(candidate).netloc.casefold()
            if candidate_host.endswith("youtube.com") or candidate_host.endswith("youtu.be"):
                return candidate
        return None

    @classmethod
    def parse_watch_html(cls, html: str) -> tuple[Optional[datetime], Optional[datetime], Optional[str]]:
        match = PLAYER_RESPONSE_RE.search(html)
        if not match:
            return None, None, None
        data = json.loads(match.group(1))
        details = data.get("videoDetails") if isinstance(data, dict) else None
        micro = data.get("microformat", {}).get("playerMicroformatRenderer", {}) if isinstance(data, dict) else {}
        title = details.get("title") if isinstance(details, dict) else None
        live = micro.get("liveBroadcastDetails") if isinstance(micro, dict) else None
        if not isinstance(live, dict):
            return None, None, title if isinstance(title, str) else None
        start_raw = live.get("startTimestamp")
        end_raw = live.get("endTimestamp")
        if not isinstance(start_raw, str):
            return None, None, title if isinstance(title, str) else None
        start = datetime.fromisoformat(start_raw.replace("Z", "+00:00")).astimezone(timezone.utc)
        end = None
        if isinstance(end_raw, str):
            end = datetime.fromisoformat(end_raw.replace("Z", "+00:00")).astimezone(timezone.utc)
        return start, end, title if isinstance(title, str) else None

    def scrape(self) -> list[TVProgram]:
        discovered_at = datetime.now(timezone.utc)
        index = self._fetch(CzechAthleticsScraper.INDEX_URL)
        targets = CzechAthleticsScraper.discover_targets(index.text, index.url)
        programs: list[TVProgram] = []
        seen_youtube: set[str] = set()

        for target in targets:
            event_response = self._fetch(target["url"])
            stream_links = self.parse_atletika_stream_links(event_response.text, event_response.url)
            for stream_link in stream_links:
                youtube_url = self._resolve_youtube_url(stream_link)
                if not youtube_url or youtube_url in seen_youtube:
                    continue
                seen_youtube.add(youtube_url)

                watch_response = self._fetch(youtube_url)
                start, end, watch_title = self.parse_watch_html(watch_response.text)
                if start is None:
                    continue

                programs.append(TVProgram(
                    source=self.source,
                    source_id=youtube_url,
                    channel="YouTube",
                    title=watch_title or target["competition"],
                    description=f"Oficiální ČAS stream: {target['competition']}",
                    start_datetime=start,
                    end_datetime=end or (start + timedelta(hours=6)),
                    source_url=youtube_url,
                    discovered_at=discovered_at,
                    timezone="Europe/Prague",
                    distribution="online",
                ))

        programs.sort(key=lambda item: item.start_datetime)
        return programs
