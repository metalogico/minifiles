"""Reject changes to migrations already included in a stable Git tag."""
from pathlib import Path
import hashlib
import json
import re
import subprocess


def git(*args):
    return subprocess.check_output(["git", *args])


root = Path(__file__).resolve().parents[2]
baseline = json.loads((root / ".github/migrations-v1.json").read_text())
for name, expected in baseline.items():
    path = root / name
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit(f"Frozen v1 migration changed: {name}. Add a new migration instead.")

# fetch-depth: 0 in CI includes stable releases, so later migrations freeze too.
for tag in git("tag", "--list").decode().splitlines():
    if not re.fullmatch(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", tag):
        continue
    paths = git("ls-tree", "-r", "--name-only", tag, "database/migrations", "backend/migrations").decode().splitlines()
    for name in paths:
        if name.endswith("/__init__.py"):
            continue
        path = root / name
        if not path.is_file() or path.read_bytes() != git("show", f"{tag}:{name}"):
            raise SystemExit(f"Released migration changed: {tag}:{name}. Add a new migration instead.")
print("Released migrations are unchanged.")
