from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

import requests

from models.tv_program import TVProgram


CHANNEL_STREAMS_URL = "https://www.youtube.com/@czechathletics/streams"
WATCH_URL = "https://www.youtube.com/watch?v={video_id}"
INITIAL_DATA_RE = re.compile(r"(?:var\s+ytInitialData\s*=|ytInitialData\s*=)\s*({.+?})\s*;\s*</script>", re.DOTALL)
PLAYER_RESPONSE_RE = re.compile(r"ytInitialPlayerResponse\s*=\s*({.+?})\s*;\s*</script>", re.DOTALL)
ATHLETICS_TERMS = (
    "atletika", "athletics", "mčr", "mcr", "hmčr", "hmcr",
    "mistrovství čr", "mistrovstvi cr", "mistrovství české republiky",
)
SENIOR_TERMS = (
    "mužů a žen", "muzu a zen", "muži a ženy", "muzi a zeny",
    "dospěl", "senior",
)
EXCLUDED_YOUTH_TERMS = (
    "žact", "zact", "dorost", "junior", "u18", "u20", "u23", "do 22",
)


class CzechAthleticsYouTubeScraper:
    """Discover official ČAS livestreams without requiring a YouTube API key."""

    source = "czechathletics_youtube"

    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130 Safari/537.36",
            "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
        })

    def _fetch(self, url: str) -> str:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.text

    @staticmethod
    def _walk(value: Any) -> Iterable[dict[str, Any]]:
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from CzechAthleticsYouTubeScraper._walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from CzechAthleticsYouTubeScraper._walk(child)

    @staticmethod
    def _text(value: Any) -> str:
        if not isinstance(value, dict):
            return ""
        if isinstance(value.get("simpleText"), str):
            return value["simpleText"].strip()
        runs = value.get("runs")
        if isinstance(runs, list):
            return "".join(str(run.get("text", "")) for run in runs if isinstance(run, dict)).strip()
        return ""

    @classmethod
    def _is_relevant(cls, title: str) -> bool:
        folded = title.casefold()
        if any(term in folded for term in EXCLUDED_YOUTH_TERMS):
            return False
        has_athletics = any(term in folded for term in ATHLETICS_TERMS)
        has_senior = any(term in folded for term in SENIOR_TERMS)
        return has_athletics and has_senior

    @classmethod
    def parse_channel_html(cls, html: str) -> list[tuple[str, str]]:
        match = INITIAL_DATA_RE.search(html)
        if not match:
            return []
        data = json.loads(match.group(1))
        found: list[tuple[str, str]] = []
        seen: set[str] = set()
        for node in cls._walk(data):
            renderer = node.get("videoRenderer") or node.get("gridVideoRenderer")
            if not isinstance(renderer, dict):
                continue
            video_id = renderer.get("videoId")
            title = cls._text(renderer.get("title"))
            if not isinstance(video_id, str) or not video_id or not title:
                continue
            if video_id in seen or not cls._is_relevant(title):
                continue
            seen.add(video_id)
            found.append((video_id, title))
        return found

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
        cards = self.parse_channel_html(self._fetch(CHANNEL_STREAMS_URL))
        programs: list[TVProgram] = []
        for video_id, card_title in cards:
            url = WATCH_URL.format(video_id=video_id)
            start, end, watch_title = self.parse_watch_html(self._fetch(url))
            title = watch_title or card_title
            if start is None or not self._is_relevant(title):
                continue
            programs.append(TVProgram(
                source=self.source,
                source_id=video_id,
                channel="YouTube",
                title=title,
                description="Oficiální online stream Českého atletického svazu",
                start_datetime=start,
                end_datetime=end or (start + timedelta(hours=6)),
                source_url=url,
                discovered_at=discovered_at,
                timezone="Europe/Prague",
                distribution="online",
            ))
        programs.sort(key=lambda item: item.start_datetime)
        return programs
