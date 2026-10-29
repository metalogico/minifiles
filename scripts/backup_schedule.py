"""MiniFiles-only configuration backup, without stopping shared services."""

import argparse
import fcntl
import json
import os
import tarfile
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.backup import snapshot

SOURCE = Path("/service")
DESTINATION = Path("/backup")
FILES = (
    ".env",
    "compose.yaml",
    "compose.https.yaml",
    "compose.backup.yaml",
    "Dockerfile",
    "requirements.txt",
    "requirements-dev.txt",
    "backend",
    "frontend",
    "scripts",
    "README.md",
    "docs",
    "AGENTS.md",
    "release.json",
    "docker",
    "tls-data",
)


def current_slot(now: datetime):
    day = now.date()
    if now.hour < 8:
        day -= timedelta(days=1)
        hour = 20
    else:
        hour = 20 if now.hour >= 20 else 8
    return f"{day.isoformat()}T{hour:02d}:00"


def validate_volume(source: Path, destination: Path, expected: str, separate_device=True):
    if not expected or (destination / ".volume-id").read_text().strip() != expected:
        raise RuntimeError("Invalid backup disk identity.")
    if separate_device and destination.stat().st_dev == source.stat().st_dev:
        raise RuntimeError("Backups must be stored on a disk separate from the system.")


def read_state(destination: Path):
    try:
        return json.loads((destination / "status.json").read_text())
    except FileNotFoundError:
        return {}


def write_state(destination: Path, state):
    temp = destination / "status.json.tmp"
    fd = os.open(temp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(state, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, destination / "status.json")


def run_once(source: Path, destination: Path, expected: str, slot: str, *, separate_device=True):
    validate_volume(source, destination, expected, separate_device)
    with (destination / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        timestamp = datetime.now(ZoneInfo("Europe/Rome")).strftime("%Y%m%d-%H%M%S")
        archive = destination / f"minifiles-{timestamp}-{time.time_ns() % 1000000000:09d}.tar.gz"
        with tempfile.TemporaryDirectory(prefix=".minifiles-", dir=destination) as staging:
            staging = Path(staging)
            snapshot(source / "config/minifiles.sqlite3", staging / "minifiles.sqlite3")
            temp_archive = staging / "snapshot.tar.gz"
            fd = os.open(temp_archive, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as output:
                with tarfile.open(fileobj=output, mode="w:gz") as tar:
                    tar.add(staging / "minifiles.sqlite3", arcname="config/minifiles.sqlite3")

                    def include(info):
                        if any(
                            part in ("node_modules", "__pycache__", ".pytest_cache", "dist")
                            for part in Path(info.name).parts
                        ):
                            return None
                        return info

                    for name in FILES:
                        if (source / name).exists():
                            tar.add(source / name, arcname="service/" + name, filter=include)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp_archive, archive)
        with tarfile.open(archive, "r:gz") as tar:
            if (
                "config/minifiles.sqlite3" not in tar.getnames()
                or "service/.env" not in tar.getnames()
            ):
                raise RuntimeError("Backup archive incomplete.")
        state = {"last_success": time.time(), "slot": slot, "archive": archive.name}
        write_state(destination, state)
        return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--health", action="store_true")
    args = parser.parse_args()
    expected = os.environ.get("MINIFILES_BACKUP_VOLUME_ID", "")
    os.umask(0o077)
    if args.health:
        validate_volume(SOURCE, DESTINATION, expected)
        state = read_state(DESTINATION)
        if time.time() - state.get("last_success", 0) > 14 * 3600:
            raise SystemExit("No successful backup in the last 14 hours.")
        print("MiniFiles backup is up to date.")
        return
    while True:
        try:
            slot = current_slot(datetime.now(ZoneInfo("Europe/Rome")))
            if args.once or read_state(DESTINATION).get("slot") != slot:
                state = run_once(SOURCE, DESTINATION, expected, slot)
                print("MiniFiles backup completed: " + state["archive"], flush=True)
            if args.once:
                return
            time.sleep(30)
        except Exception as exc:
            # Never log configuration contents or credentials.
            print("MiniFiles backup failed: " + type(exc).__name__, flush=True)
            if args.once:
                raise SystemExit(1)
            time.sleep(900)


if __name__ == "__main__":
    main()
