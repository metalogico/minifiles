import sqlite3
import tarfile
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from backend.database import Database
from scripts.backup_schedule import current_slot, read_state, run_once, validate_volume


@pytest.mark.parametrize(
    "hour, expected",
    [
        (7, "2026-10-26T20:00"),
        (8, "2026-10-27T08:00"),
        (19, "2026-10-27T08:00"),
        (20, "2026-10-27T20:00"),
    ],
)
def test_twice_daily_local_slots(hour, expected):
    assert current_slot(datetime(2026, 10, 27, hour, tzinfo=ZoneInfo("Europe/Rome"))) == expected


def test_configuration_archive_and_restore(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "backup"
    destination.mkdir()
    (destination / ".volume-id").write_text("test-volume")
    db = Database(source / "config")
    section = {"id": "books", "name": "Books", "path": "Books", "color": "blue", "position": 0}
    db.save_section(section)
    (source / ".env").write_text("MINIFILES_PASSWORD=test-only-value\n")
    (source / "compose.yaml").write_text("name: minifiles\n")
    (source / "compose.https.yaml").write_text("services: {https: {image: caddy}}\n")
    (source / "docker").mkdir()
    (source / "docker/Caddyfile").write_text("https://localhost:8443 { tls internal }\n")
    (source / "tls-data/caddy/pki").mkdir(parents=True)
    (source / "tls-data/caddy/pki/root.key").write_bytes(b"test-only-ca-key")
    state = run_once(source, destination, "test-volume", "2026-10-27T08:00", separate_device=False)
    archive = destination / state["archive"]
    assert archive.stat().st_mode & 0o777 == 0o600
    assert read_state(destination)["slot"] == "2026-10-27T08:00"
    with tarfile.open(archive) as tar:
        assert tar.extractfile("service/.env").read() == (source / ".env").read_bytes()
        assert tar.extractfile("service/tls-data/caddy/pki/root.key").read() == b"test-only-ca-key"
        for name in ("compose.https.yaml", "docker/Caddyfile"):
            assert tar.extractfile("service/" + name).read() == (source / name).read_bytes()
        restored = tmp_path / "restored.sqlite3"
        restored.write_bytes(tar.extractfile("config/minifiles.sqlite3").read())
    with sqlite3.connect(restored) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT name FROM sections").fetchone()[0] == "Books"
    with pytest.raises(RuntimeError):
        validate_volume(source, destination, "wrong-volume", separate_device=False)
    with pytest.raises(RuntimeError):
        validate_volume(source, destination, "test-volume")
