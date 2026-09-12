from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from scrapers.idnes import BASE_URL, IdnesTVScraper, ParsedSchedule


DETAIL_DATETIME_RE = re.compile(
    r"(?P<day>\d{1,2})\.\s*(?P<month>\d{1,2})\.\s*(?P<year>\d{4}),\s*"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})"
)


class LiveIdnesTVScraper(IdnesTVScraper):
    """iDNES scraper that uses channel pages only for discovery.

    The real iDNES channel schedule is a wide table and does not use the same
    surrounding date/time markup as search results. We therefore use the
    channel page to discover relevant detail URLs, then parse the stable detail
    page where title, exact date/time and description are explicit.
    """

    def _fetch_detail_html(self, url: str) -> str:
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
            return page.content()
        finally:
            page.close()

    def _channel_candidate_urls(self, html: str, page_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        urls: list[str] = []
        seen: set[str] = set()
        for anchor in soup.find_all("a", href=True):
            href = urljoin(page_url, anchor["href"])
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
            if value.casefold() in {"sport", "sportovní"}:
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
        detail_links = self._detail_link_count(html, url)
        if detail_links == 0:
            raise RuntimeError(
                "iDNES returned channel HTML without programme detail links "
                f"for channel {channel_slug!r}; html_len={len(html)}"
            )

        candidate_urls = self._channel_candidate_urls(html, url)
        kept = 0
        for detail_url in candidate_urls:
            item = self.parse_detail_html(
                self._fetch_detail_html(detail_url),
                detail_url,
            )
            if not self._is_sport_relevant(item):
                continue
            kept += 1
            yield item

        print(
            f"[IDNES] channel={channel_slug!r} page={url} html={len(html)} "
            f"detail_links={detail_links} candidates={len(candidate_urls)} kept={kept}"
        )
