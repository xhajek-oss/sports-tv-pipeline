import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from models.sports_event import SportsEvent
from .base import BaseScraper


TIME_RE = re.compile(r"^(?P<time>\d{1,2}:\d{2})\s+(?P<name>.+)$")
ROW_RE = re.compile(
    r"^(?P<local>\d{1,2}:\d{2})\s+"
    r"(?P<my>\d{1,2}:\d{2})\s+"
    r"(?P<sex>[MWX])\s+"
    r"(?P<event>.+?)\s+"
    r"(?P<round>Final|Semi(?:-final)?|Heat.*|Qualification.*|Round.*)$",
    re.I,
)


class WorldAthleticsScraper(BaseScraper):
    source = "worldathletics"

    TARGETS = [
        {
            "kind": "budapest",
            "competition": "World Athletics Ultimate Championship",
            "location": "Budapest",
            "country": "HUN",
            "timezone": "Europe/Budapest",
            "dates": ["2026-09-11", "2026-09-12", "2026-09-13"],
            "url": (
                "https://worldathletics.org/competitions/"
                "world-athletics-ultimate-championship/2026/schedule"
            ),
        },
        {
            "kind": "copenhagen",
            "competition": "World Athletics Road Running Championships",
            "location": "Copenhagen",
            "country": "DEN",
            "timezone": "Europe/Copenhagen",
            "dates": ["2026-09-19", "2026-09-20"],
            "url": (
                "https://worldathletics.org/competitions/"
                "world-athletics-road-running-championships/copenhagen26/timetable"
            ),
        },
    ]

    @staticmethod
    def _event(target, name, local_dt, source_id):
        return SportsEvent(
            source="worldathletics",
            source_id=source_id,
            sport="athletics",
            competition=target["competition"],
            name=name,
            start_datetime=local_dt.astimezone(timezone.utc),
            end_datetime=None,
            location=target["location"],
            country=target["country"],
            source_url=target["url"],
            discovered_at=datetime.now(timezone.utc),
            timezone=target["timezone"],
        )

    @staticmethod
    def _local_dt(date_text, time_text, tz_name):
        naive = datetime.strptime(
            f"{date_text} {time_text}", "%Y-%m-%d %H:%M"
        )
        return naive.replace(tzinfo=ZoneInfo(tz_name))

    def _parse_copenhagen(self, page, target):
        events = []

        day_buttons = page.locator("button").filter(has_text=re.compile(r"DAY\s+[12]", re.I))
        if day_buttons.count() < 2:
            raise RuntimeError("World Athletics Copenhagen day tabs not found")

        for day_index, date_text in enumerate(target["dates"]):
            button = day_buttons.nth(day_index)
            button.click()
            page.wait_for_timeout(700)

            rows = page.locator("tbody tr")
            found_this_day = 0

            for i in range(rows.count()):
                text = re.sub(r"\s+", " ", rows.nth(i).inner_text()).strip()
                match = ROW_RE.match(text)
                if not match:
                    continue

                sex = match.group("sex").upper()
                event_name = match.group("event").strip()
                round_name = match.group("round").strip()
                local_time = match.group("local")

                gender = {"W": "Women", "M": "Men", "X": "Mixed"}.get(sex, sex)
                name = f"{event_name} {round_name} {gender}"

                local_dt = self._local_dt(
                    date_text, local_time, target["timezone"]
                )
                source_id = (
                    f"copenhagen26:{date_text}:{local_time}:"
                    f"{sex}:{event_name}:{round_name}"
                )
                events.append(self._event(target, name, local_dt, source_id))
                found_this_day += 1

            if found_this_day == 0:
                raise RuntimeError(
                    f"World Athletics Copenhagen: no timetable rows for {date_text}"
                )

        return events

    def _parse_budapest(self, page, target):
        # The Budapest schedule is rendered as three visual columns. DOM text
        # order interleaves the columns, so we use browser layout (x position)
        # to assign each event card to Friday/Saturday/Sunday.
        cards = page.evaluate(
            """() => {
                const timeRe = /^\\s*\\d{1,2}:\\d{2}\\s+/;
                const out = [];

                for (const el of document.querySelectorAll('body *')) {
                    const text = (el.innerText || '').replace(/\\s+/g, ' ').trim();
                    if (!timeRe.test(text) || text.length > 140) continue;

                    // Keep the smallest useful element: if a child already
                    // contains the same complete event text, the parent is noise.
                    let childHasSame = false;
                    for (const child of el.children) {
                        const childText = (child.innerText || '')
                            .replace(/\\s+/g, ' ').trim();
                        if (childText === text) {
                            childHasSame = true;
                            break;
                        }
                    }
                    if (childHasSame) continue;

                    const r = el.getBoundingClientRect();
                    if (r.width <= 0 || r.height <= 0) continue;

                    out.push({
                        text,
                        x: Math.round(r.x),
                        y: Math.round(r.y),
                        width: Math.round(r.width),
                        height: Math.round(r.height)
                    });
                }
                return out;
            }"""
        )

        parsed = []
        seen_text_pos = set()

        for card in cards:
            text = card["text"]
            match = TIME_RE.match(text)
            if not match:
                continue

            name = match.group("name").strip()
            # Reject session headers such as "19:00 - 22:00 Local time".
            if "local time" in name.lower() or re.match(r"^-\s*\d", name):
                continue

            key = (text, card["x"], card["y"])
            if key in seen_text_pos:
                continue
            seen_text_pos.add(key)

            parsed.append(card)

        if not parsed:
            raise RuntimeError("World Athletics Budapest: no event cards found")

        # Cluster event cards into three visual columns by their x centres.
        centres = sorted(card["x"] + card["width"] / 2 for card in parsed)
        min_x, max_x = centres[0], centres[-1]
        if max_x - min_x < 100:
            raise RuntimeError(
                "World Athletics Budapest: schedule columns could not be separated"
            )

        step = (max_x - min_x) / 2
        anchors = [min_x, min_x + step, max_x]

        buckets = [[], [], []]
        for card in parsed:
            centre = card["x"] + card["width"] / 2
            idx = min(range(3), key=lambda i: abs(centre - anchors[i]))
            buckets[idx].append(card)

        events = []
        for day_index, bucket in enumerate(buckets):
            bucket.sort(key=lambda item: item["y"])
            date_text = target["dates"][day_index]

            # Budapest cards are nested: e.g. both "4x100m Relay" and
            # "4x100m Relay Final Mixed" can appear at the same coordinates.
            # Keep the most complete text only when one candidate is a strict
            # prefix/subset of another candidate at the same time and position.
            candidates = []
            for card in bucket:
                match = TIME_RE.match(card["text"])
                if not match:
                    continue
                candidates.append({
                    "time": match.group("time"),
                    "name": match.group("name").strip(),
                    "x": card["x"],
                    "y": card["y"],
                })

            keep = [True] * len(candidates)
            for i, short in enumerate(candidates):
                short_norm = re.sub(r"\s+", " ", short["name"]).strip().lower()
                for j, long in enumerate(candidates):
                    if i == j:
                        continue
                    if short["time"] != long["time"]:
                        continue
                    if abs(short["x"] - long["x"]) > 8 or abs(short["y"] - long["y"]) > 8:
                        continue

                    long_norm = re.sub(r"\s+", " ", long["name"]).strip().lower()
                    if (
                        len(long_norm) > len(short_norm)
                        and (
                            long_norm.startswith(short_norm)
                            or short_norm in long_norm
                        )
                    ):
                        keep[i] = False
                        break

            seen = set()
            for candidate, should_keep in zip(candidates, keep):
                if not should_keep:
                    continue

                time_text = candidate["time"]
                name = candidate["name"]
                dedupe_key = (date_text, time_text, name.lower())
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                local_dt = self._local_dt(
                    date_text, time_text, target["timezone"]
                )
                source_id = (
                    f"budapest2026:{date_text}:{time_text}:"
                    f"{re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')}"
                )
                events.append(self._event(target, name, local_dt, source_id))

        # Official programme has many events across all three days; this catches
        # structural breakage without hard-coding an exact count.
        if len(events) < 20 or any(not bucket for bucket in buckets):
            raise RuntimeError(
                f"World Athletics Budapest: suspicious timetable parse "
                f"({len(events)} events, columns={[len(b) for b in buckets]})"
            )

        return events

    def scrape(self):
        all_events = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="en-GB")

            try:
                for target in self.TARGETS:
                    page = context.new_page()
                    try:
                        response = page.goto(
                            target["url"],
                            wait_until="domcontentloaded",
                            timeout=60_000,
                        )
                        if response and response.status >= 400:
                            raise RuntimeError(
                                f"World Athletics returned HTTP {response.status}"
                            )

                        page.wait_for_timeout(3500)

                        if target["kind"] == "budapest":
                            events = self._parse_budapest(page, target)
                        else:
                            events = self._parse_copenhagen(page, target)

                        all_events.extend(events)
                        print(
                            f"worldathletics {target['location']}: "
                            f"found {len(events)} events"
                        )
                    finally:
                        page.close()
            finally:
                context.close()
                browser.close()

        return all_events
