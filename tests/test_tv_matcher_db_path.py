import sqlite3
from pathlib import Path

import pytest

import matching.tv_matcher as tv_matcher
from matching.tv_matcher import TVMatcher


def create_db(path: Path, *, sports: bool = True, tv: bool = True) -> None:
    conn = sqlite3.connect(path)
    try:
        if sports:
            conn.execute("CREATE TABLE sports_events (id INTEGER PRIMARY KEY, start_datetime TEXT)")
        if tv:
            conn.execute("CREATE TABLE tv_programs (id INTEGER PRIMARY KEY, start_datetime TEXT)")
        conn.commit()
    finally:
        conn.close()


def test_default_db_path_is_repo_relative(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    matcher = TVMatcher()
    assert matcher.db_path == tv_matcher.PROJECT_ROOT / "data" / "sports_events.db"


def test_explicit_db_path_works(tmp_path):
    db_path = tmp_path / "custom.db"
    create_db(db_path)
    matcher = TVMatcher(db_path)
    with matcher._connect() as conn:
        assert conn.execute("SELECT 1").fetchone()[0] == 1


def test_missing_db_has_clear_error(tmp_path):
    matcher = TVMatcher(tmp_path / "missing.db")
    with pytest.raises(RuntimeError, match="SQLite database does not exist"):
        matcher._connect()


@pytest.mark.parametrize(
    ("sports", "tv", "missing"),
    [
        (False, True, "sports_events"),
        (True, False, "tv_programs"),
    ],
)
def test_missing_required_table_has_clear_error(tmp_path, sports, tv, missing):
    db_path = tmp_path / "partial.db"
    create_db(db_path, sports=sports, tv=tv)
    matcher = TVMatcher(db_path)
    with pytest.raises(RuntimeError, match=missing):
        matcher._connect()
