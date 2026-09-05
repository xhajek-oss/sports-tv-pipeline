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


def test_state_store_only_reports_transitions(tmp_path):
    path = tmp_path / "health.json"
    state = HealthStateStore(path)
    warning = classify_health(source="idnes", count=0, allow_empty=False)
    assert state.record(warning) == "new_problem"
    state.save()

    state2 = HealthStateStore(path)
    assert state2.record(warning) is None
    healthy = classify_health(source="idnes", count=5, allow_empty=False)
    assert state2.record(healthy) == "recovered"
