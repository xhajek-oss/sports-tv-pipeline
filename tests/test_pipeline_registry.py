from app.registry import SOURCES, selected_sources


def test_registry_contains_expected_sources():
    assert set(SOURCES) == {"idnes", "atletika_cz", "czechathletics_youtube"}


def test_selected_sources_supports_single_and_all():
    assert [item.name for item in selected_sources("idnes")] == ["idnes"]
    assert len(selected_sources("all")) == len(SOURCES)


def test_youtube_can_have_no_scheduled_streams():
    assert SOURCES["czechathletics_youtube"].allow_empty is True
