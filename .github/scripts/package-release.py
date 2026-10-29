"""Assemble an installation bundle from an explicit list, never the local .env."""
from pathlib import Path
import hashlib
import io
import os
import re
import subprocess
import tarfile

root = Path(__file__).resolve().parents[2]
version = os.environ["RELEASE_VERSION"]
if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
    raise SystemExit("Expected a stable semantic version without v")
project = "minifiles"
files = ["compose.yaml", ".env.example", "README.md", "LICENSE",
         "docs/RELEASING.md", "docs/UPGRADING.md"]
for name in ("compose.https.yaml", "compose.minipc.yaml", "compose.backup.yaml"):
    if (root / name).exists():
        files.append(name)
if project == "soloinventory":
    files.append("docker/Caddyfile")
# Only tracked public docs can enter the archive; ignored operational notes stay private.
files.extend(subprocess.check_output(["git", "ls-files", "docs"], cwd=root, text=True).splitlines())
out = root / "dist-release"
out.mkdir(exist_ok=True)
archive = out / f"{project}-{version}-install.tar.gz"
with tarfile.open(archive, "w:gz") as tar:
    for name in sorted(set(files)):
        data = (root / name).read_bytes()
        if name.endswith(".yaml") or name == ".env.example":
            data = re.sub(rb"(ghcr\.io/metalogico/[a-z-]+:)[0-9]+\.[0-9]+\.[0-9]+", lambda m: m[1] + version.encode(), data)
        info = tarfile.TarInfo(name)
        info.size = len(data)
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(data))
checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
(out / "SHA256SUMS").write_text(f"{checksum}  {archive.name}\n")
print(archive.name)
