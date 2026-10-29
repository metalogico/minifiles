import json
import sqlite3
import time
from contextlib import contextmanager


class Database:
    def __init__(self, root):
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "minifiles.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sections (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    color TEXT NOT NULL,
                    position INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def sections(self):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM sections ORDER BY position, rowid")
            return [dict(row) for row in rows]

    def save_section(self, section):
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO sections VALUES (:id, :name, :path, :color, :position)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    path = excluded.path,
                    color = excluded.color,
                    position = excluded.position
                """,
                section,
            )

    def remove_section(self, section_id):
        with self.connect() as db:
            db.execute("DELETE FROM sections WHERE id=?", (section_id,))

    def cached_stats(self):
        with self.connect() as db:
            row = db.execute("SELECT value FROM cache WHERE key='stats'").fetchone()
        return json.loads(row[0]) if row else {"updated_at": None, "sections": {}}

    def save_stats(self, sections):
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO cache VALUES ('stats',?)",
                (json.dumps({"updated_at": time.time(), "sections": sections}),),
            )
