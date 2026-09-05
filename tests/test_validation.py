from datetime import datetime, timezone
from types import SimpleNamespace

from validation.event_validator import EventCountValidator


def event(day: int):
    return SimpleNamespace(
        start_datetime=datetime(2026, 9, day, 12, tzinfo=timezone.utc)
    )


def test_warns_on_large_drop(tmp_path):
    path = tmp_path / "state.json"
    validator = EventCountValidator(path)
    validator.current["test"] = {
        "count": 20,
        "earliest_start": "2026-09-10T12:00:00+00:00",
        "latest_start": "2026-09-30T12:00:00+00:00",
        "validated_at": "2026-09-01T00:00:00+00:00",
    }
    validator.save()

    validator = EventCountValidator(path)
    result = validator.validate(
        "test",
        [event(i) for i in range(10, 15)],
        now=datetime(2026, 9, 3, tzinfo=timezone.utc),
    )
    assert result.warnings
    assert "20 -> 5" in result.warnings[0]


def test_no_warning_after_previous_schedule_finished(tmp_path):
    path = tmp_path / "state.json"
    validator = EventCountValidator(path)
    validator.current["test"] = {
        "count": 32,
        "earliest_start": "2026-09-04T12:00:00+00:00",
        "latest_start": "2026-09-05T21:00:00+00:00",
        "validated_at": "2026-09-05T00:00:00+00:00",
    }
    validator.save()

    validator = EventCountValidator(path)
    result = validator.validate(
        "test",
        [],
        now=datetime(2026, 9, 6, 12, tzinfo=timezone.utc),
    )
    assert result.warnings == []


def test_first_run_is_baseline_only(tmp_path):
    validator = EventCountValidator(tmp_path / "state.json")
    result = validator.validate(
        "test",
        [],
        now=datetime(2026, 9, 3, tzinfo=timezone.utc),
    )
    assert result.previous_count is None
    assert result.warnings == []
