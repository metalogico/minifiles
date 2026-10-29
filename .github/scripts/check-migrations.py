"""Reject changes to migrations already included in main or a stable Git tag."""
from pathlib import Path
import hashlib
import json
import re
import subprocess


def git(*args):
    return subprocess.check_output(["git", *args], cwd=root)


root = Path(__file__).resolve().parents[2]
baseline = json.loads((root / ".github/migrations-v1.json").read_text())
for name, expected in baseline.items():
    path = root / name
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit(f"Frozen v1 migration changed: {name}. Add a new migration instead.")

# Fetch origin/main and tags before checking a development branch locally.
references = [
    tag for tag in git("tag", "--list").decode().splitlines()
    if re.fullmatch(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", tag)
]
main = subprocess.run(
    ["git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"], cwd=root
)
if main.returncode == 0:
    references.append("origin/main")
for tag in references:
    paths = git("ls-tree", "-r", "--name-only", tag, "database/migrations", "backend/migrations").decode().splitlines()
    for name in paths:
        if name.endswith("/__init__.py"):
            continue
        path = root / name
        if not path.is_file() or path.read_bytes() != git("show", f"{tag}:{name}"):
            raise SystemExit(f"Released migration changed: {tag}:{name}. Add a new migration instead.")
print("Released migrations are unchanged.")
