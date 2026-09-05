from __future__ import annotations

import json
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.registry import SourceSpec, selected_sources
from matching.tv_matcher import TVMatcher
from monitoring.health import HealthResult, HealthStateStore, classify_health, jsonable
from monitoring.telegram import format_transition, send_telegram
from storage.sqlite import SQLiteStorage
from validation.event_validator import EventCountValidator


@dataclass(frozen=True)
class SourceRun:
    source: str
    kind: str
    count: int
    status: str
    message: str


class PipelineRunner:
    def __init__(
        self,
        *,
        db_path: str = "data/sports_events.db",
        validation_state: str = "data/validation_state.json",
        health_state: str = "data/health_state.json",
        artifact_dir: str = "artifacts/debug",
    ) -> None:
        self.db_path = db_path
        self.validation_state = validation_state
        self.health_state = health_state
        self.artifact_dir = Path(artifact_dir)

    @staticmethod
    def _close_scraper(scraper: object) -> None:
        close = getattr(scraper, "_close_browser", None)
        if callable(close):
            close()

    def _write_debug(self, source: str, *, items: Iterable[object] = (), error: Exception | None = None) -> None:
        target = self.artifact_dir / source
        target.mkdir(parents=True, exist_ok=True)
        payload = [jsonable(item) for item in items]
        (target / "parsed.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if error is not None:
            (target / "error.txt").write_text(
                "".join(traceback.format_exception(type(error), error, error.__traceback__)),
                encoding="utf-8",
            )

    def _scrape(self, spec: SourceSpec) -> tuple[list[object], Exception | None]:
        scraper = spec.factory()
        try:
            return list(scraper.scrape()), None
        except Exception as exc:
            return [], exc
        finally:
            self._close_scraper(scraper)

    def run_pr(self) -> list[SourceRun]:
        # PR mode intentionally avoids external websites. Unit tests plus registry
        # validation make this a deterministic pre-merge gate.
        results = []
        for spec in selected_sources("all"):
            scraper = spec.factory()
            source = getattr(scraper, "source", None)
            self._close_scraper(scraper)
            if not source:
                raise RuntimeError(f"{spec.name}: scraper has no source identifier")
            results.append(SourceRun(spec.name, spec.kind, 0, "ready", "registry ok"))
        return results

    def run_health(self, source: str = "all") -> list[SourceRun]:
        state = HealthStateStore(self.health_state)
        results: list[SourceRun] = []
        for spec in selected_sources(source):
            items, error = self._scrape(spec)
            health = classify_health(
                source=spec.name,
                count=len(items),
                allow_empty=spec.allow_empty,
                error=error,
            )
            transition = state.record(health)
            print(
                f"[HEALTH] source={spec.name} status={health.status} "
                f"count={health.count} message={health.message}"
            )
            if transition:
                try:
                    send_telegram(format_transition(health, transition))
                except Exception as exc:
                    print(f"[TELEGRAM] ERROR: {exc}")
            results.append(SourceRun(spec.name, spec.kind, len(items), health.status, health.message))
        state.keep_unchecked_previous()
        state.save()
        return results

    def run_debug(self, source: str) -> list[SourceRun]:
        if source == "all":
            raise ValueError("Debug mode requires one explicit source")
        results: list[SourceRun] = []
        for spec in selected_sources(source):
            items, error = self._scrape(spec)
            self._write_debug(spec.name, items=items, error=error)
            if error:
                print(f"[DEBUG] source={spec.name} ERROR: {error}")
                results.append(SourceRun(spec.name, spec.kind, 0, "down", str(error)))
            else:
                print(f"[DEBUG] source={spec.name} items={len(items)} artifact={self.artifact_dir / spec.name}")
                results.append(SourceRun(spec.name, spec.kind, len(items), "healthy", "debug artifacts written"))
        return results

    def run_production(self, source: str = "all") -> list[SourceRun]:
        storage = SQLiteStorage(self.db_path)
        validator = EventCountValidator(self.validation_state)
        results: list[SourceRun] = []
        try:
            for spec in selected_sources(source):
                print(f"[PROD] scraping {spec.name}...")
                items, error = self._scrape(spec)
                if error is not None:
                    if spec.kind == "sports":
                        validator.keep_previous(spec.name)
                    print(f"[PROD] {spec.name}: ERROR: {error}; previous DB data preserved")
                    results.append(SourceRun(spec.name, spec.kind, 0, "down", str(error)))
                    continue

                warnings: list[str] = []
                if spec.kind == "sports":
                    validation = validator.validate(spec.name, items)
                    warnings = validation.warnings
                    for item in items:
                        storage.upsert(item)
                else:
                    for item in items:
                        storage.upsert_tv_program(item)

                status = "warning" if warnings else "healthy"
                message = "; ".join(warnings) if warnings else "ok"
                print(f"[PROD] {spec.name}: {len(items)} items status={status}")
                results.append(SourceRun(spec.name, spec.kind, len(items), status, message))

            validator.save()
        finally:
            storage.close()

        # Matching is meaningful only when both sports and TV data are present in
        # the restored/current production database.
        if source == "all" or "idnes" in source.split(","):
            try:
                matches = TVMatcher(self.db_path).find_candidates(min_score=50)
                print(f"[PROD] matcher candidates={len(matches)}")
            except Exception as exc:
                print(f"[PROD] matcher ERROR: {exc}")
                results.append(SourceRun("tv_matcher", "matcher", 0, "down", str(exc)))
        return results

    def run(self, *, mode: str, source: str = "all") -> list[SourceRun]:
        if mode == "pr":
            return self.run_pr()
        if mode == "health":
            return self.run_health(source)
        if mode == "debug":
            return self.run_debug(source)
        if mode == "production":
            return self.run_production(source)
        raise ValueError(f"Unknown mode: {mode}")
