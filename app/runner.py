from __future__ import annotations

import json
import re
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.registry import SourceSpec, selected_sources
from delivery.digest import build_today_digest
from delivery.weekly import build_next_week_report
from matching.tv_matcher import TVMatcher
from monitoring.health import HealthStateStore, classify_health, jsonable
from monitoring.telegram import format_transition, send_digest, send_telegram
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
    def __init__(self, *, db_path: str = "data/sports_events.db", validation_state: str = "data/validation_state.json", health_state: str = "data/health_state.json", artifact_dir: str = "artifacts/debug") -> None:
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
        (target / "parsed.json").write_text(json.dumps([jsonable(item) for item in items], ensure_ascii=False, indent=2), encoding="utf-8")
        if error is not None:
            (target / "error.txt").write_text("".join(traceback.format_exception(type(error), error, error.__traceback__)), encoding="utf-8")

    def _scrape(self, spec: SourceSpec) -> tuple[list[object], Exception | None]:
        scraper = spec.factory()
        try:
            return list(scraper.scrape()), None
        except Exception as exc:
            return [], exc
        finally:
            self._close_scraper(scraper)

    def run_pr(self) -> list[SourceRun]:
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
            health = classify_health(source=spec.name, count=len(items), allow_empty=spec.allow_empty, error=error)
            transition = state.record(health)
            print(f"[HEALTH] source={spec.name} status={health.status} count={health.count} message={health.message}")
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
        removed = storage.purge_non_snow_biathlon()
        if removed:
            print(f"[PROD] removed {removed} legacy non-snow biathlon races")
        validator = EventCountValidator(self.validation_state)
        results: list[SourceRun] = []
        selected = selected_sources(source)
        try:
            for spec in selected:
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
                    if spec.name == "hcdynamo" and items and not warnings:
                        removed_stale = storage.reconcile_hcdynamo(items)
                        print(f"[PROD] hcdynamo: reconciled {removed_stale} stale future fixtures")
                    if spec.name == "biathlonworld" and items and not warnings:
                        removed_stale = storage.reconcile_biathlon(items)
                        print(f"[PROD] biathlonworld: reconciled {removed_stale} stale future races")
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

        if source == "all" or any(spec.kind == "tv" for spec in selected):
            try:
                matches = TVMatcher(self.db_path).find_candidates(min_score=50)
                print(f"[PROD] matcher candidates={len(matches)}")
            except Exception as exc:
                print(f"[PROD] matcher ERROR: {exc}")
                results.append(SourceRun("tv_matcher", "matcher", 0, "down", str(exc)))
        return results

    def run_digest_preview(self) -> list[SourceRun]:
        """Render digest without making any Telegram API request."""
        try:
            message = build_today_digest(self.db_path)
            if not message:
                print("[DIGEST PREVIEW] no qualifying live broadcasts today")
                return [SourceRun("digest_preview", "delivery", 0, "healthy", "nothing to preview")]
            message = re.sub(r"(🏆 [^\\n]+)\\n\\n", r"\\1\\n", message)
            print("[DIGEST PREVIEW] BEGIN")
            print(message)
            print("[DIGEST PREVIEW] END (not sent)")
            return [SourceRun("digest_preview", "delivery", 1, "healthy", "preview only; not sent")]
        except Exception as exc:
            print(f"[DIGEST PREVIEW] ERROR: {exc}")
            return [SourceRun("digest_preview", "delivery", 0, "down", str(exc))]

    def run_digest(self) -> list[SourceRun]:
        try:
            message = build_today_digest(self.db_path)
            if not message:
                print("[DIGEST] no qualifying live broadcasts today; nothing sent")
                return [SourceRun("telegram_digest", "delivery", 0, "healthy", "nothing to send")]
            message = re.sub(r"(🏆 [^\n]+)\n\n", r"\1\n", message)
            sent = send_digest(message)
            if not sent:
                return [SourceRun("telegram_digest", "delivery", 0, "warning", "TELEGRAM_BOT_TOKEN or TELEGRAM_DIGEST_CHAT_ID not configured")]
            print("[DIGEST] Telegram digest sent")
            return [SourceRun("telegram_digest", "delivery", 1, "healthy", "sent")]
        except Exception as exc:
            print(f"[DIGEST] ERROR: {exc}")
            return [SourceRun("telegram_digest", "delivery", 0, "down", str(exc))]

    def run_weekly_tv_diagnostic(self) -> list[SourceRun]:
        """Explain missing weekly TV assignments; never send messages."""
        import sqlite3
        from datetime import timedelta
        from delivery.weekly import collect_next_week_events
        from matching.tv_matcher import _parse_dt, _hockey_matchups, score_pair

        events = [e for e in collect_next_week_events(self.db_path) if e.sport == "hockey" and not e.broadcasts]
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            sports = {row["id"]: row for row in conn.execute("SELECT * FROM sports_events")}
            tv_rows = conn.execute("SELECT * FROM tv_programs").fetchall()
        print(f"[WEEKLY TV DIAGNOSTIC] unmatched_hockey={len(events)}")
        for event in events:
            row = sports[event.event_id]
            start = _parse_dt(row["start_datetime"])
            nearby = []
            for tv in tv_rows:
                tv_start = _parse_dt(tv["start_datetime"])
                if not start or not tv_start or abs(tv_start - start) > timedelta(hours=5):
                    continue
                candidate = score_pair(row, tv)
                matchups = _hockey_matchups((tv["title"] or "") + "\\n" + (tv["description"] or ""))
                nearby.append((abs((tv_start - start).total_seconds()), tv, candidate, bool(matchups)))
            nearby.sort(key=lambda item: item[0])
            print(f"[WEEKLY TV DIAGNOSTIC] EVENT {event.start.isoformat()} {event.name}; nearby_tv={len(nearby)}")
            for _, tv, candidate, explicit_matchup in nearby[:15]:
                print(f"[WEEKLY TV DIAGNOSTIC] TV channel={tv['channel']!r} start={tv['start_datetime']} title={tv['title']!r} score={candidate.score} status={candidate.status} explicit_matchup={explicit_matchup} reasons={candidate.reasons}")
            if not nearby:
                print("[WEEKLY TV DIAGNOSTIC] No TV schedule entries within five hours")
        return [SourceRun("weekly_tv_diagnostic", "diagnostic", len(events), "healthy", "read-only; no Telegram sent")]

    def run_weekly_preview(self) -> list[SourceRun]:
        """Print next week's report without contacting Telegram."""
        try:
            message = build_next_week_report(self.db_path)
            if not message:
                print("[WEEKLY PREVIEW] no sports events next week")
                return [SourceRun("weekly_preview", "delivery", 0, "healthy", "nothing to preview")]
            print("[WEEKLY PREVIEW] BEGIN")
            print(message)
            print("[WEEKLY PREVIEW] END (not sent)")
            return [SourceRun("weekly_preview", "delivery", 1, "healthy", "preview only; not sent")]
        except Exception as exc:
            print(f"[WEEKLY PREVIEW] ERROR: {exc}")
            return [SourceRun("weekly_preview", "delivery", 0, "down", str(exc))]

    def run_weekly(self) -> list[SourceRun]:
        try:
            message = build_next_week_report(self.db_path)
            if not message:
                print("[WEEKLY] no sports events next week; nothing sent")
                return [SourceRun("telegram_weekly", "delivery", 0, "healthy", "nothing to send")]
            sent = send_digest(message)
            if not sent:
                return [SourceRun("telegram_weekly", "delivery", 0, "warning", "TELEGRAM_BOT_TOKEN or TELEGRAM_DIGEST_CHAT_ID not configured")]
            print("[WEEKLY] Telegram weekly report sent")
            return [SourceRun("telegram_weekly", "delivery", 1, "healthy", "sent")]
        except Exception as exc:
            print(f"[WEEKLY] ERROR: {exc}")
            return [SourceRun("telegram_weekly", "delivery", 0, "down", str(exc))]

    def run(self, *, mode: str, source: str = "all") -> list[SourceRun]:
        if mode == "pr": return self.run_pr()
        if mode == "health": return self.run_health(source)
        if mode == "debug": return self.run_debug(source)
        if mode == "production": return self.run_production(source)
        if mode == "digest_preview": return self.run_digest_preview()
        if mode == "digest": return self.run_digest()
        if mode == "weekly_tv_diagnostic": return self.run_weekly_tv_diagnostic()
        if mode == "weekly_preview": return self.run_weekly_preview()
        if mode == "weekly": return self.run_weekly()
        raise ValueError(f"Unknown mode: {mode}")
