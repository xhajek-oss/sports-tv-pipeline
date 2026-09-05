import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


@dataclass
class ValidationResult:
    source: str
    count: int
    previous_count: int | None
    warnings: list[str]


class EventCountValidator:
    """Compare scraper output with the previous successful GitHub Actions run.

    Warnings never stop scraping. State is written only after the whole run,
    so a source exception does not overwrite its last known-good baseline.
    """

    def __init__(
        self,
        state_path: str | Path = "data/validation_state.json",
        drop_ratio: float = 0.50,
        min_previous_count: int = 5,
    ):
        self.state_path = Path(state_path)
        self.drop_ratio = drop_ratio
        self.min_previous_count = min_previous_count
        self.previous = self._load()
        self.current: dict[str, dict] = {}

    def _load(self) -> dict:
        if not self.state_path.exists():
            return {}

        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        if not isinstance(data, dict):
            return {}

        sources = data.get("sources", data)
        return sources if isinstance(sources, dict) else {}

    @staticmethod
    def _iso(dt: datetime | None) -> str | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _parse_iso(value: object) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def validate(
        self,
        source: str,
        events: Iterable,
        now: datetime | None = None,
    ) -> ValidationResult:
        events = list(events)
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)

        starts = []
        for event in events:
            dt = getattr(event, "start_datetime", None)
            if dt is None:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            starts.append(dt.astimezone(timezone.utc))

        count = len(events)
        earliest = min(starts) if starts else None
        latest = max(starts) if starts else None

        previous = self.previous.get(source, {})
        previous_count = previous.get("count")
        if not isinstance(previous_count, int):
            previous_count = None
        previous_latest = self._parse_iso(previous.get("latest_start"))

        warnings: list[str] = []

        previous_schedule_finished = (
            previous_latest is not None and previous_latest < now
        )

        if (
            previous_count is not None
            and previous_count >= self.min_previous_count
            and not previous_schedule_finished
            and count < previous_count
        ):
            ratio = count / previous_count if previous_count else 1.0
            if count == 0:
                warnings.append(
                    f"{source}: suspicious drop {previous_count} -> 0 events"
                )
            elif ratio <= self.drop_ratio:
                warnings.append(
                    f"{source}: suspicious drop {previous_count} -> {count} events "
                    f"({ratio:.0%} of previous run)"
                )

        self.current[source] = {
            "count": count,
            "earliest_start": self._iso(earliest),
            "latest_start": self._iso(latest),
            "validated_at": now.isoformat(),
        }

        return ValidationResult(
            source=source,
            count=count,
            previous_count=previous_count,
            warnings=warnings,
        )

    def keep_previous(self, source: str) -> None:
        if source in self.previous:
            self.current[source] = self.previous[source]

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "sources": self.current,
        }
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp.replace(self.state_path)
