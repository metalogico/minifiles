"""Apply ordered schema changes without rewriting an installed database's version."""

import sqlite3

from backend.migrations.v001_initial import apply as initial_schema

MIGRATIONS = (initial_schema,)


def migrate(db: sqlite3.Connection) -> None:
    # A write lock keeps the version check and migration in one transaction.
    # Do not use executescript here: it can commit a pending transaction.
    db.execute("BEGIN IMMEDIATE")
    try:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version > len(MIGRATIONS):
            raise RuntimeError(
                "Database schema is newer than this MiniFiles version. "
                "Use an image that supports this database schema."
            )
        for index in range(version, len(MIGRATIONS)):
            MIGRATIONS[index](db)
            db.execute(f"PRAGMA user_version={index + 1}")
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.execute("PRAGMA journal_mode=WAL")
