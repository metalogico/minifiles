"""Create a consistent SQLite snapshot; the media volume is backed up separately."""

import argparse
import os
import sqlite3
from pathlib import Path


def snapshot(source: Path, destination: Path):
    if not source.is_file():
        raise SystemExit("Database not found.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        with (
            sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src,
            sqlite3.connect(destination) as dst,
        ):
            src.backup(dst)
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("SQLite snapshot integrity check failed.")
    except BaseException:
        destination.unlink()
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(os.environ.get("MINIFILES_CONFIG_ROOT", "/config")) / "minifiles.sqlite3",
    )
    args = parser.parse_args()
    snapshot(args.source, args.destination)
    print("SQLite snapshot verified.")
