from backend.database import Database
from scripts.backup import snapshot


def test_backup_and_restore(tmp_path):
    db = Database(tmp_path / "source")
    section = {"id": "books", "name": "Libri", "path": "Books", "color": "blue", "position": 0}
    db.save_section(section)
    copy = tmp_path / "backup.sqlite3"
    snapshot(db.path, copy)
    restored_root = tmp_path / "restored"
    restored_root.mkdir()
    (restored_root / "minifiles.sqlite3").write_bytes(copy.read_bytes())
    restored = Database(restored_root)
    assert restored.sections() == [section]
