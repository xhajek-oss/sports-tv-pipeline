from app.registry import SOURCES, selected_sources


def test_registry_contains_expected_sources():
    assert {"hcdynamo", "biathlonworld", "iihf", "diamondleague", "worldathletics", "idnes"} <= set(SOURCES)


def test_selected_sources_supports_single_and_all():
    assert [item.name for item in selected_sources("idnes")] == ["idnes"]
    assert len(selected_sources("all")) == len(SOURCES)


def test_iihf_allows_empty_schedule():
    assert SOURCES["iihf"].allow_empty is True
