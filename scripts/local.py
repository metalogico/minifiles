"""Explicit loopback-only test environment, with private generated credentials."""

import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
env_file = ROOT / ".env.local"
if not env_file.exists():
    content = (
        "MINIFILES_USERNAME=demo\n"
        f"MINIFILES_PASSWORD={secrets.token_urlsafe(24)}\n"
        "MINIFILES_ORIGIN=https://127.0.0.1:8090\n"
        f"MINIFILES_UID={os.getuid()}\n"
        f"MINIFILES_GID={os.getgid()}\n"
    )
    fd = os.open(env_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(content)
for line in env_file.read_text().splitlines():
    if line and not line.startswith("#"):
        key, value = line.split("=", 1)
        os.environ[key] = value
for folder in ("local-data", "local-config", "tls-data"):
    (ROOT / folder).mkdir(mode=0o700, exist_ok=True)
if "--init-only" in sys.argv:
    print("Test environment ready. Private credentials are in .env.local.")
    raise SystemExit(0)
# Direct development server is loopback-only HTTP; Docker uses the HTTPS proxy.
os.environ["MINIFILES_ORIGIN"] = (
    "http://127.0.0.1:5173" if "--vite" in sys.argv else "http://127.0.0.1:8090"
)
os.environ["MINIFILES_DATA_ROOT"] = str(ROOT / "local-data")
os.environ["MINIFILES_CONFIG_ROOT"] = str(ROOT / "local-config")
os.chdir(ROOT)
os.execv(
    sys.executable,
    [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.main:create_app",
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        "8090",
        "--workers",
        "1",
        "--no-proxy-headers",
    ],
)
