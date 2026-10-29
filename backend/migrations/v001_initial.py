"""Version 1: the original sections and statistics schema. Keep this file immutable."""

import sqlite3


def apply(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS sections (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            path TEXT NOT NULL,
            color TEXT NOT NULL,
            position INTEGER NOT NULL
        )
    """)
    db.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
