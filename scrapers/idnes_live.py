from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Iterable
from urllib.parse import urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from matching.idnes_rules import LIVE, REPLAY, classify, is_candidate
from matching.tv_matcher import _norm

from scrapers.idnes import BASE_URL, IdnesTVScraper, ParsedSchedule


GRID_BASE_RE = re.compile(r"\bden:\s*new Date\((\d+)\)")
DETAIL_DATETIME_RE = re.compile(
    r"(?P<day>\d{1,2})\.\s*(?P<month>\d{1,2})\.\s*(?P<year>\d{4}),\s*"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})"
)


class LiveIdnesTVScraper(IdnesTVScraper):
    """Read the HTML programme grid and open ambiguous candidate details."""

    def _fetch_html(self, url: str) -> str:
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            return super()._fetch_html(url)

    def _fetch_detail_html(self, url: str) -> str:
        return self._fetch_html(url)

    def _card_schedule(self, anchor: Tag, url: str, base: datetime | None) -> ParsedSchedule | None:
        parts = self._detail_parts(url)
        title = anchor.select_one("h3")
        if parts is None or base is None or title is None:
            return None
        try:
            start = base + timedelta(minutes=int(anchor["data-start"]))
            end = (start.astimezone(timezone.utc) + timedelta(minutes=int(anchor["data-length"]))).astimezone(self.tz)
        except (KeyError, ValueError, OverflowError):
            return None
        day = ("po", "ut", "st", "ct", "pa", "so", "ne")[start.weekday()]
        if (day, start.hour, start.minute) != (parts["dow"], int(parts["hour"]), int(parts["minute"])):
            return None
        paragraphs = [p.get_text(" ", strip=True) for p in anchor.select("p")]
        description = " ".join(text for text in paragraphs if text)
        if anchor.select_one(".x-live"):
            description = f"{description}; Živě" if description else "Živě"
        return ParsedSchedule(
            self._source_id(url) or "", parts["channel"], title.get_text(" ", strip=True),
            description or None, start, end, url,
        )

    def _channel_candidate_urls(self, html: str, page_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        urls: list[str] = []
        seen: set[str] = set()
        for anchor in soup.find_all("a", href=True):
            href = urljoin(page_url, anchor["href"])
            if urlparse(href).hostname != urlparse(BASE_URL).hostname:
                continue
            if not self._source_id(href) or not self._detail_parts(href):
                continue
            evidence = " ".join(anchor.stripped_strings).strip()
            if not evidence:
                continue
            relevant = any(
                self._is_query_relevant(query, evidence)
                for query in self.search_queries
            )
            if not relevant or href in seen:
                continue
            seen.add(href)
            urls.append(href)
        return urls

    def parse_detail_html(self, html: str, source_url: str) -> ParsedSchedule:
        source_id = self._source_id(source_url)
        parts = self._detail_parts(source_url)
        if not source_id or not parts:
            raise ValueError(f"Not an iDNES programme detail URL: {source_url}")

        channel_slug = parts["channel"].lower()
        if channel_slug not in self.channels:
            raise ValueError(f"Unconfigured iDNES channel: {channel_slug}")

        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.find("h1")
        if not isinstance(h1, Tag):
            raise RuntimeError(f"iDNES detail page has no h1: {source_url}")
        title = " ".join(h1.stripped_strings).strip()
        if not title:
            raise RuntimeError(f"iDNES detail page has empty title: {source_url}")

        values: list[str] = []
        started = False
        for node in h1.next_elements:
            if isinstance(node, Tag) and node.name == "h1" and node is not h1:
                break
            if not isinstance(node, str):
                continue
            text = " ".join(node.split())
            if not text:
                continue
            if text == title and not started:
                continue
            if "Přidat do mého TV programu" in text:
                break
            values.append(text)
            started = True

        joined = " ; ".join(values)
        dt_match = DETAIL_DATETIME_RE.search(joined)
        if not dt_match:
            raise RuntimeError(f"iDNES detail page has no explicit date/time: {source_url}")

        local_date = datetime(
            int(dt_match.group("year")),
            int(dt_match.group("month")),
            int(dt_match.group("day")),
            int(dt_match.group("hour")),
            int(dt_match.group("minute")),
            tzinfo=self.tz,
        )

        description_parts: list[str] = []
        after_datetime = False
        for value in values:
            if not after_datetime:
                if DETAIL_DATETIME_RE.search(value):
                    after_datetime = True
                continue
            if value.casefold() in {"sport", "sportovní", "sdílet", "pořad"}:
                continue
            if value.casefold().startswith("zpět na televizní program"):
                continue
            description_parts.append(value)

        description = " ; ".join(description_parts).strip(" ;") or None
        if description:
            description = description[:1500]

        # iDNES detail pages expose the exact start but not the end. Four hours
        # is a conservative envelope used only for overlap matching; report
        # output always shows the exact start time from iDNES.
        end_local = local_date + timedelta(hours=4)

        return ParsedSchedule(
            source_id=source_id,
            channel_slug=channel_slug,
            title=title,
            description=description,
            start_local=local_date,
            end_local=end_local,
            source_url=source_url,
        )

    def _scrape_channel(self, channel_slug: str) -> Iterable[ParsedSchedule]:
        url = urljoin(BASE_URL, channel_slug)
        html = self._fetch_html(url)
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("a[data-show][href]")
        if not cards:
            if not self._detail_link_count(html, url):
                raise RuntimeError(f"iDNES programme grid is missing for {channel_slug}")
            # Compatibility with layouts exposing only detail links.
            for detail_url in self._channel_candidate_urls(html, url):
                item = self.parse_detail_html(self._fetch_detail_html(detail_url), detail_url)
                if self._is_sport_relevant(item):
                    yield item
            return

        pages = [(html, cards)]
        # The default grid can show fewer days than the complete weekly report.
        # The guide's own navigation uses the date and numeric channel ID.
        if self.extend_schedule:
            channel_id = cards[0].get("data-channel")
            if channel_id and channel_id.isdecimal():
                later = self.now.date() + timedelta(days=7)
                query = urlencode({"dt": f"{later.day}.{later.month}.{later.year}", "program": channel_id})
                later_html = self._fetch_html(f"{BASE_URL}?{query}")
                later_cards = BeautifulSoup(later_html, "html.parser").select("a[data-show][href]")
                later_cards = [card for card in later_cards if card.get("data-channel") == channel_id]
                if not later_cards:
                    raise RuntimeError(f"iDNES later programme grid is missing for {channel_slug}")
                pages.append((later_html, later_cards))

        seen: set[str] = set()
        for page_html, page_cards in pages:
            yield from self._parse_cards(page_html, page_cards, url, seen)
        print(f"[IDNES] channel={channel_slug} cards={len(seen)}")

    def _parse_cards(
        self, html: str, cards: list[Tag], url: str, seen: set[str],
    ) -> Iterable[ParsedSchedule]:
        match = GRID_BASE_RE.search(html)
        base = datetime.fromtimestamp(int(match[1]) / 1000, self.tz) if match else None
        for anchor in cards:
            detail_url = urljoin(url, anchor["href"])
            if urlparse(detail_url).hostname != urlparse(BASE_URL).hostname or detail_url in seen:
                continue
            seen.add(detail_url)
            if not is_candidate(anchor.get_text(" ", strip=True)) or not self._source_id(detail_url):
                continue
            item = self._card_schedule(anchor, detail_url, base)
            summary = (item.description or "").removesuffix("; Živě").strip() if item else ""
            truncated = summary.endswith(("...", "…"))
            if item and not truncated and classify(item.title, item.description):
                yield item
                continue
            if item and item.description:
                if REPLAY.search(_norm(summary)):
                    continue
                # A complete summary has already provided the same evidence as the
                # detail. Empty, visibly shortened or missing summaries need a read.
                if len(summary.split()) > 3 and not truncated:
                    continue
                if _norm(summary) == "zive":
                    summary = ""
                if summary and not truncated and not LIVE.search(_norm(item.description)):
                    continue
            detail = self.parse_detail_html(self._fetch_detail_html(detail_url), detail_url)
            if item and item.description and item.description.endswith("Živě"):
                detail = replace(detail, description=f"{detail.description or ''}; Živě".strip("; "))
            if classify(detail.title, detail.description):
                yield detail
