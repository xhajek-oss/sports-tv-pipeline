from monitoring.health import DOWN, HEALTHY, WARNING, HealthStateStore, classify_health


def test_health_classification_error_is_down():
    result = classify_health(source="idnes", count=0, allow_empty=False, error=RuntimeError("boom"))
    assert result.status == DOWN
    assert "boom" in result.message


def test_health_classification_unexpected_empty_is_warning():
    result = classify_health(source="idnes", count=0, allow_empty=False)
    assert result.status == WARNING


def test_health_classification_allowed_empty_is_healthy():
    result = classify_health(source="iihf", count=0, allow_empty=True)
    assert result.status == HEALTHY


def test_state_store_alerts_after_two_consecutive_failures(tmp_path):
    path = tmp_path / "health.json"
    warning = classify_health(source="idnes", count=0, allow_empty=False)
    healthy = classify_health(source="idnes", count=5, allow_empty=False)

    first = HealthStateStore(path)
    assert first.record(warning) is None
    assert first.current["idnes"]["consecutive_failures"] == 1
    first.save()

    second = HealthStateStore(path)
    assert second.record(warning) == "new_problem"
    assert second.current["idnes"]["alerted"] is True
    second.save()

    third = HealthStateStore(path)
    assert third.record(warning) is None
    third.save()

    recovered = HealthStateStore(path)
    assert recovered.record(healthy) == "recovered"
    assert recovered.current["idnes"]["consecutive_failures"] == 0
    recovered.save()

    again = HealthStateStore(path)
    assert again.record(warning) is None


def test_health_success_between_failures_resets_counter(tmp_path):
    path = tmp_path / "health.json"
    down = classify_health(source="diamondleague", count=0, allow_empty=True, error=RuntimeError("failed"))
    healthy = classify_health(source="diamondleague", count=0, allow_empty=True)
    for result in (down, healthy, down):
        state = HealthStateStore(path)
        assert state.record(result) is None
        state.save()
    state = HealthStateStore(path)
    assert state.record(down) == "new_problem"


def test_unchecked_sources_keep_their_failure_streak(tmp_path):
    path = tmp_path / "health.json"
    down = classify_health(source="idnes", count=0, allow_empty=False, error=RuntimeError("failed"))
    state = HealthStateStore(path)
    state.record(down)
    state.save()
    state = HealthStateStore(path)
    state.keep_unchecked_previous()
    state.save()
    state = HealthStateStore(path)
    assert state.record(down) == "new_problem"


def test_legacy_down_state_recovers_without_duplicate_alert(tmp_path):
    import json
    path = tmp_path / "health.json"
    path.write_text(json.dumps({"sources": {"idnes": {"status": "down"}}}), encoding="utf-8")
    state = HealthStateStore(path)
    assert state.record(classify_health(source="idnes", count=1, allow_empty=False)) == "recovered"
