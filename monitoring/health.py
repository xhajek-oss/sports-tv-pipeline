from __future__ import annotations

import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


HEALTHY = "healthy"
WARNING = "warning"
DOWN = "down"


@dataclass(frozen=True)
class HealthResult:
    source: str
    status: str
    count: int
    message: str
    checked_at: str


def classify_health(
    *,
    source: str,
    count: int,
    allow_empty: bool,
    error: Exception | None = None,
    warnings: Iterable[str] = (),
) -> HealthResult:
    now = datetime.now(timezone.utc).isoformat()
    if error is not None:
        return HealthResult(source, DOWN, count, f"{type(error).__name__}: {error}", now)
    warning_list = list(warnings)
    if warning_list:
        return HealthResult(source, WARNING, count, "; ".join(warning_list), now)
    if count == 0 and not allow_empty:
        return HealthResult(source, WARNING, 0, "unexpected empty result", now)
    return HealthResult(source, HEALTHY, count, "ok", now)


class HealthStateStore:
    def __init__(self, path: str | Path = "data/health_state.json") -> None:
        self.path = Path(path)
        self.previous = self._load()
        self.current: dict[str, dict[str, Any]] = {}

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        sources = payload.get("sources", {}) if isinstance(payload, dict) else {}
        return sources if isinstance(sources, dict) else {}

    def record(self, result: HealthResult) -> str | None:
        previous_status = self.previous.get(result.source, {}).get("status")
        self.current[result.source] = asdict(result)
        if previous_status is None:
            return None if result.status == HEALTHY else "new_problem"
        if previous_status == result.status:
            return None
        if result.status == HEALTHY:
            return "recovered"
        return "new_problem"

    def keep_unchecked_previous(self) -> None:
        for source, state in self.previous.items():
            self.current.setdefault(source, state)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "sources": self.current,
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)


def jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value
