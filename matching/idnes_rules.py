from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from matching.tv_matcher import _hockey_team, _norm

LIVE = re.compile(r"\b(?:primy prenos|live|zive)\b")
REPLAY = re.compile(r"\b(?:zaznam|repriza|sestrih|highlights|archiv|opakovani)\b")
EXTRA = re.compile(r"\b(?:studio|magazin|preview|biatlonista roku)\b")
NON_SENIOR_WINTER = re.compile(r"\b(?:junior\w*|dorost\w*|youth|letni|summer|roller\w*|city biathlon|loop one)\b")
HOCKEY = re.compile(r"\b(?:hokej\w*|hockey|elh|tipsport extralig\w*|iihf)\b")
DURATION = re.compile(r"\s*\(\d+\s*min\)\s*$", re.I)
ROUTE = re.compile(r"^.*?\bOneplay Sport (MD\d+)\s*[-–]\s*ELH:\s*", re.I)
LIVE_PREFIX = re.compile(r"^Přímý přenos\s+(?:(?:hokejového\s+)?utkání\s+)?", re.I)
TEAM_SEPARATOR = re.compile(r"\s+[-–—]\s+|[–—]")
COMPACT_SEPARATOR = re.compile(r"(?<=Pardubice)-|-(?=(?:HC|HK|BK|Dynamo)\s)", re.I)
HockeyTeams = tuple[str, str]


@dataclass(frozen=True)
class Rule:
    id: str
    sport: str
    label: str
    match: re.Pattern[str]
    teams: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class Selection:
    rule: Rule
    name: str
    key: str
    route: str | None = None


@lru_cache(maxsize=1)
def rules() -> tuple[Rule, ...]:
    path = Path(__file__).resolve().parents[1] / "config" / "watched_sports.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    return tuple(
        Rule(item["id"], item["sport"], item["label"], re.compile(item["match"]),
             tuple(re.compile(team) for team in item.get("teams", ())))
        for item in config["competitions"] if item.get("enabled", True)
    )


def is_candidate(text: str) -> bool:
    """Include generic headings whose description can supply the missing context."""
    text = _norm(text)
    return bool(re.search(r"\b(?:atletik\w*|athletics|biatlon\w*|biathlon|ibu)\b", text)
                or any(rule.match.search(text) or any(team.search(text) for team in rule.teams)
                       for rule in rules()))


def _fixture_sides(text: str) -> list[str]:
    sides = TEAM_SEPARATOR.split(text)
    if len(sides) == 1:
        sides = text.split("-") if text.count("-") == 1 else COMPACT_SEPARATOR.split(text)
    return sides


def _fixtures(title: str, description: str):
    title_fixture = re.sub(r"^(?:(?:lední hokej|hokej|ELH|Tipsport (?:ELH|extraliga))\s*:\s*)+", "", title, flags=re.I)
    fragments = [title_fixture, *re.split(r"[;|\n•]+|(?<=[.!?])\s+", description)]
    seen: set[tuple[HockeyTeams, str | None]] = set()
    for fragment in fragments:
        fragment = fragment.strip()
        route = ROUTE.match(fragment)
        if route:
            fragment = fragment[route.end():]
        fragment = LIVE_PREFIX.sub("", fragment)
        fragment = re.split(r"\b(?:Přímý přenos|Živě|Záznam)\b", fragment, maxsplit=1, flags=re.I)[0]
        fragment = re.sub(r"\s*\([^)]*\)\s*$", "", fragment).strip(" .,:")
        raw_teams = _fixture_sides(fragment)
        if len(raw_teams) != 2:
            continue
        home, away = (_hockey_team(team) for team in raw_teams)
        if home == away or any(not re.search(r"[a-z]", team) for team in (home, away)):
            continue
        pair = (
            "dynamo pardubice" if home == "pardubice" else home,
            "dynamo pardubice" if away == "pardubice" else away,
        )
        identity = (tuple(sorted(pair)), route[1].upper() if route else None)
        if identity not in seen:
            seen.add(identity)
            yield pair, " – ".join(team.strip() for team in raw_teams), identity[1]


def _watch_fixture(rule: Rule, teams: HockeyTeams) -> bool:
    return not rule.teams or any(pattern.fullmatch(team) for pattern in rule.teams for team in teams)


def needs_hockey_detail(title: str, description: str) -> bool:
    text = _norm(f"{title} {description}")
    if not HOCKEY.search(text) or EXTRA.search(_norm(title)):
        return False
    fixtures = list(_fixtures(title, description))
    for rule in rules():
        if rule.sport != "hockey":
            continue
        if rule.match.search(text) and not fixtures:
            return True
        if any(_watch_fixture(rule, teams) for teams, _, _ in fixtures):
            # The card identifies a watched fixture but may lack competition
            # or live evidence that is only present on the detail page.
            return True
    return False


def classify(title: str, description: str | None, *, live: bool = False) -> list[Selection]:
    description = description or ""
    headline = _norm(title)
    text = _norm(f"{title} {description}")
    # Explicit replays and surrounding programmes can share a competition name.
    if REPLAY.search(headline) or REPLAY.search(_norm(description)) or EXTRA.search(headline):
        return []
    if not live and not LIVE.search(text):
        return []
    if re.search(r"\b(?:ms|mistrovstvi sveta) v lednim hokeji zen\b", text):
        return []
    for rule in rules():
        if not rule.match.search(text):
            continue
        if rule.sport == "hockey":
            if not HOCKEY.search(text):
                continue
            return [
                Selection(rule, name, "|".join(sorted(pair)), route)
                for pair, name, route in _fixtures(title, description)
                if _watch_fixture(rule, pair)
            ]
        if rule.sport == "biathlon" and NON_SENIOR_WINTER.search(text):
            return []
        # The card description usually supplies the discipline or meeting.
        name = DURATION.sub("", description.split(";", 1)[0]).strip(" .") or title
        name = LIVE_PREFIX.sub("", name).strip(" ,:-") or title
        name = name[:1].upper() + name[1:]
        return [Selection(rule, name, _norm(name))]
    return []
