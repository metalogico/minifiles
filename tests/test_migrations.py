import sqlite3

import pytest

from backend.database import Database
from backend.migrations import migrate
from backend.migrations.v001_initial import apply as initial_schema


def test_existing_v1_database_keeps_sections_and_cache(tmp_path):
    with sqlite3.connect(tmp_path / "minifiles.sqlite3") as db:
        initial_schema(db)
        db.execute("PRAGMA user_version=1")
        db.execute("INSERT INTO sections VALUES ('books', 'Books', 'Books', '#123456', 0)")
        db.execute("INSERT INTO cache VALUES ('stats', '{\"sections\": {\"books\": 42}}')")

    database = Database(tmp_path)
    assert database.sections()[0]["name"] == "Books"
    assert database.cached_stats()["sections"] == {"books": 42}
    with database.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1


def test_new_database_is_initialized_once(tmp_path):
    database = Database(tmp_path)
    database.save_section(dict(id="one", name="One", path="One", color="blue", position=0))
    assert Database(tmp_path).sections() == database.sections()


def test_newer_schema_is_rejected_without_changing_data(tmp_path):
    path = tmp_path / "minifiles.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=999")
        db.execute("CREATE TABLE future_data (value TEXT)")
        db.execute("INSERT INTO future_data VALUES ('keep me')")

    with pytest.raises(RuntimeError, match="newer"):
        Database(tmp_path)

    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 999
        assert db.execute("SELECT value FROM future_data").fetchone()[0] == "keep me"
        assert db.execute("SELECT name FROM sqlite_master WHERE name='sections'").fetchone() is None


def test_failed_migration_rolls_back_schema_and_version(monkeypatch):
    def fail(db):
        db.execute("CREATE TABLE incomplete (value TEXT)")
        raise RuntimeError("migration failed")

    monkeypatch.setattr("backend.migrations.MIGRATIONS", (initial_schema, fail))
    with sqlite3.connect(":memory:") as db:
        with pytest.raises(RuntimeError, match="migration failed"):
            migrate(db)
        assert db.execute("PRAGMA user_version").fetchone()[0] == 0
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
