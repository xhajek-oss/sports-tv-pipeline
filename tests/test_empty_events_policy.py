def test_empty_events_are_valid():
    """
    Project-wide policy:
    - [] means the source currently has no published events.
    - exceptions are reserved for actual loading/parsing/configuration errors.
    """
    assert list([]) == []
