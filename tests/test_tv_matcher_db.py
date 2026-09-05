from pathlib import Path

import pytest

from matching.tv_matcher import TVMatcher


def test_default_db_path_matches_sqlite_storage():
    assert TVMatcher().db_path == Path("data/sports_events.db")


def test_missing_database_has_clear_error(tmp_path):
    matcher = TVMatcher(tmp_path / "missing.db")
    with pytest.raises(RuntimeError, match="does not exist"):
        matcher.find_candidates()
