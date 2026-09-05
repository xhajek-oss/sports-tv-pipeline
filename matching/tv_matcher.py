from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

PRAGUE = ZoneInfo("Europe/Prague")
UTC = timezone.utc
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class MatchCandidate:
    sports_event_id: int
    tv_program_id: int
    score: int
    status: str
    reasons: tuple[str, ...]


ATHLETICS_TERMS = (
    "atletika", "athletics", "diamond league", "diamantova liga",
    "world athletics", "mcr v atletice", "beh: atletika",
)
HOCKEY_TERMS = (
    "hokej", "hockey", "elh", "extraliga", "maxa liga",
    "dynamo pardubice", "hc ", "studio hokej", "buly",
)
BIATHLON_TERMS = ("biatlon", "biathlon")

COMPETITION_GROUPS = {
    "diamond_league": ("diamond league", "diamantova liga"),
    "world_athletics_ultimate": (
        "world athletics ultimate championship",
        "ultimate championship",
    ),
    "iihf": ("iihf", "mistrovstvi sveta", "world championship"),
    "extraliga": ("elh", "extraliga"),
}

DISCIPLINE_GROUPS = {
    "100m": (r"\b100\s*m\b",),
    "200m": (r"\b200\s*m\b",),
    "400m": (r"\b400\s*m\b",),
    "800m": (r"\b800\s*m\b",),
    "1500m": (r"\b1500\s*m\b",),
    "5000m": (r"\b5000\s*m\b",),
    "10000m": (r"\b10000\s*m\b",),
    "hurdles": (r"hurdle", r"prekaz"),
    "high_jump": (r"high jump", r"vysk"),
    "long_jump": (r"long jump", r"dalk"),
    "triple_jump": (r"triple jump", r"trojskok"),
    "pole_vault": (r"pole vault", r"tyc"),
    "shot_put": (r"shot put", r"koule"),
    "discus": (r"discus", r"disk"),
    "javelin": (r"javelin", r"ostep"),
}


def _norm(value: Optional[str]) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().replace("–", "-").replace("—", "-")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _sport(text: str) -> Optional[str]:
    if any(x in text for x in ATHLETICS_TERMS):
        return "athletics"
    if any(x in text for x in BIATHLON_TERMS):
        return "biathlon"
    if any(x in text for x in HOCKEY_TERMS):
        return "hockey"
    return None


def _competition(text: str) -> Optional[str]:
    for key, terms in COMPETITION_GROUPS.items():
        if any(term in text for term in terms):
            return key
    return None


def _disciplines(text: str) -> set[str]:
    found: set[str] = set()
    for key, patterns in DISCIPLINE_GROUPS.items():
        if any(re.search(pattern, text) for pattern in patterns):
            found.add(key)
    return found


def _gender(text: str) -> Optional[str]:
    words = set(text.split())
    if words & {"women", "woman", "zen", "zeny", "zen"}:
        return "women"
    if words & {"men", "man", "muzi", "muzu", "muz"}:
        return "men"
    return None


def _round(text: str) -> Optional[str]:
    if "semifinal" in text or "semifinale" in text:
        return "semi"
    if "final" in text or "finale" in text:
        return "final"
    return None


def _hockey_team(value: str) -> str:
    """Normalize a team name while retaining its identifying words."""
    team = _norm(value)
    words = team.split()
    while words and words[0] in {"elh", "hokej", "extraliga"}:
        words.pop(0)
    if words and words[0] in {"hc", "bk"}:
        words.pop(0)
    if words and words[-1] == "hk":
        words.pop()
    return " ".join(words)


def _hockey_matchup(value: Optional[str]) -> Optional[frozenset[str]]:
    """Return two normalized teams for titles shaped like 'Team A - Team B'."""
    if not value:
        return None
    clean = value.replace("–", "-").replace("—", "-")
    match = re.search(r"(?:^|:\s*)(.+?)\s+-\s+(.+?)(?:\s*\([^)]*\))?$", clean)
    if not match:
        return None
    teams = frozenset(_hockey_team(part) for part in match.groups())
    if len(teams) != 2 or "" in teams:
        return None
    return teams


def _event_text(row: sqlite3.Row) -> str:
    return _norm(" ".join(str(row[k] or "") for k in ("sport", "competition", "name", "location", "country")))


def _tv_text(row: sqlite3.Row) -> str:
    return _norm(" ".join(str(row[k] or "") for k in ("channel", "title", "description")))


def score_pair(event: sqlite3.Row, tv: sqlite3.Row) -> MatchCandidate:
    event_start = _parse_dt(event["start_datetime"])
    event_end = _parse_dt(event["end_datetime"])
    tv_start = _parse_dt(tv["start_datetime"])
    tv_end = _parse_dt(tv["end_datetime"])
    assert event_start and tv_start

    e_text = _event_text(event)
    t_text = _tv_text(tv)
    reasons: list[str] = []
    score = 0

    e_sport = _sport(e_text) or _norm(event["sport"])
    t_sport = _sport(t_text)
    if t_sport and e_sport == t_sport:
        score += 20
        reasons.append(f"sport:{e_sport}")
    elif t_sport and e_sport != t_sport:
        return MatchCandidate(event["id"], tv["id"], 0, "no_match", ("sport_conflict",))

    # A specific hockey broadcast must name the same two teams as the event.
    # Broad studio/magazine programmes have no matchup, so they remain eligible
    # for the existing time/sport scoring as "possible" candidates.
    if e_sport == "hockey" and t_sport == "hockey":
        event_matchup = _hockey_matchup(event["name"])
        tv_matchup = _hockey_matchup(tv["title"])
        if event_matchup and tv_matchup:
            if event_matchup != tv_matchup:
                return MatchCandidate(
                    event["id"], tv["id"], 0, "no_match", ("team_conflict",)
                )
            score += 15
            reasons.append("team_matchup")

    # TV blocks often cover several individual events. If end is missing,
    # allow a conservative 3-hour window for broad sports programming.
    effective_tv_end = tv_end or (tv_start + timedelta(hours=3))
    effective_event_end = event_end or event_start
    overlaps = event_start <= effective_tv_end and effective_event_end >= tv_start
    delta_minutes = abs((event_start - tv_start).total_seconds()) / 60

    if overlaps:
        score += 40
        reasons.append("time_overlap")
    elif delta_minutes <= 30:
        score += 32
        reasons.append(f"time_near:{int(delta_minutes)}m")
    elif delta_minutes <= 90:
        score += 20
        reasons.append(f"time_near:{int(delta_minutes)}m")
    elif delta_minutes <= 180:
        score += 8
        reasons.append(f"time_near:{int(delta_minutes)}m")
    else:
        return MatchCandidate(event["id"], tv["id"], score, "no_match", tuple(reasons + ["time_too_far"]))

    e_comp = _competition(e_text)
    t_comp = _competition(t_text)
    if e_comp and t_comp:
        if e_comp == t_comp:
            score += 20
            reasons.append(f"competition:{e_comp}")
        else:
            score -= 15
            reasons.append("competition_conflict")
    elif e_comp and e_comp.replace("_", " ") in t_text:
        score += 15
        reasons.append("competition_text")

    e_disc = _disciplines(e_text)
    t_disc = _disciplines(t_text)
    if e_disc and t_disc:
        if e_disc & t_disc:
            score += 12
            reasons.append("discipline")
        else:
            score -= 8
            reasons.append("discipline_conflict")
    elif e_disc and not t_disc:
        # Broad TV block: no discipline in title is not a penalty.
        reasons.append("broad_tv_block")

    e_gender = _gender(e_text)
    t_gender = _gender(t_text)
    if e_gender and t_gender:
        if e_gender == t_gender:
            score += 5
            reasons.append(f"gender:{e_gender}")
        else:
            score -= 8
            reasons.append("gender_conflict")

    e_round = _round(e_text)
    t_round = _round(t_text)
    if e_round and t_round:
        if e_round == t_round:
            score += 3
            reasons.append(f"round:{e_round}")
        else:
            score -= 4
            reasons.append("round_conflict")

    location = _norm(event["location"])
    if location and len(location) >= 4 and location in t_text:
        score += 5
        reasons.append("location")

    score = max(0, min(100, score))
    status = "match" if score >= 70 else "possible" if score >= 50 else "no_match"
    return MatchCandidate(event["id"], tv["id"], score, status, tuple(reasons))


class TVMatcher:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = (
            PROJECT_ROOT / "data" / "sports_events.db"
            if db_path is None
            else Path(db_path).expanduser().resolve()
        )

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise RuntimeError(
                f"SQLite database does not exist: {self.db_path}. "
                "Run the sports scraper and TV scraper first."
            )
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        required = {"sports_events", "tv_programs"}
        missing = sorted(required - tables)
        if missing:
            conn.close()
            raise RuntimeError(
                f"SQLite database {self.db_path} is missing required table(s): "
                + ", ".join(missing)
            )
        return conn

    def find_candidates(self, *, min_score: int = 50, days_before: int = 1, days_after: int = 1) -> list[MatchCandidate]:
        with self._connect() as conn:
            events = conn.execute("SELECT * FROM sports_events ORDER BY start_datetime").fetchall()
            tv_rows = conn.execute("SELECT * FROM tv_programs ORDER BY start_datetime").fetchall()

        tv_index = [(row, _parse_dt(row["start_datetime"])) for row in tv_rows]
        results: list[MatchCandidate] = []

        for event in events:
            event_start = _parse_dt(event["start_datetime"])
            if not event_start:
                continue
            lo = event_start - timedelta(days=days_before)
            hi = event_start + timedelta(days=days_after)
            for tv, tv_start in tv_index:
                if not tv_start or tv_start < lo or tv_start > hi:
                    continue
                candidate = score_pair(event, tv)
                if candidate.score >= min_score:
                    results.append(candidate)

        results.sort(key=lambda x: (-x.score, x.sports_event_id, x.tv_program_id))
        return results

    def candidate_details(
        self, candidates: Iterable[MatchCandidate]
    ) -> list[tuple[MatchCandidate, sqlite3.Row, sqlite3.Row]]:
        items = list(candidates)
        if not items:
            return []

        event_ids = sorted({item.sports_event_id for item in items})
        tv_ids = sorted({item.tv_program_id for item in items})
        event_placeholders = ",".join("?" for _ in event_ids)
        tv_placeholders = ",".join("?" for _ in tv_ids)

        with self._connect() as conn:
            events = {
                row["id"]: row
                for row in conn.execute(
                    f"SELECT * FROM sports_events WHERE id IN ({event_placeholders})",
                    event_ids,
                )
            }
            tv_rows = {
                row["id"]: row
                for row in conn.execute(
                    f"SELECT * FROM tv_programs WHERE id IN ({tv_placeholders})",
                    tv_ids,
                )
            }

        details = []
        for item in items:
            event = events.get(item.sports_event_id)
            tv = tv_rows.get(item.tv_program_id)
            if event is not None and tv is not None:
                details.append((item, event, tv))
        return details

    def best_matches(self, *, min_score: int = 50) -> list[MatchCandidate]:
        best: dict[int, MatchCandidate] = {}
        for candidate in self.find_candidates(min_score=min_score):
            current = best.get(candidate.sports_event_id)
            if current is None or candidate.score > current.score:
                best[candidate.sports_event_id] = candidate
        return sorted(best.values(), key=lambda x: x.sports_event_id)
