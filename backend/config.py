import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    data_root: Path
    config_root: Path
    username: str
    password: str
    origin: str
    secure_cookie: bool = False
    session_seconds: int = 43200
    upload_idle_seconds: int = 120
    ticket_seconds: int = 600
    max_uploads: int = 4
    max_upload_bytes: int = 0
    reserve_bytes: int = 1024 * 1024 * 1024
    frontend: Path = Path(__file__).resolve().parents[1] / "frontend/dist"

    @classmethod
    def from_env(cls) -> "Settings":
        username = os.environ.get("MINIFILES_USERNAME", "")
        password = os.environ.get("MINIFILES_PASSWORD", "")
        origin = os.environ.get("MINIFILES_ORIGIN", "").rstrip("/")
        if not username or not password or password == "CHANGE_ME":
            raise RuntimeError("Set MINIFILES_USERNAME and MINIFILES_PASSWORD.")
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise RuntimeError("MINIFILES_ORIGIN must be the exact web origin, without a path.")
        if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise RuntimeError("HTTPS is required outside loopback development.")
        for key, minimum in (
            ("MINIFILES_SESSION_SECONDS", 1),
            ("MINIFILES_UPLOAD_IDLE_SECONDS", 1),
            ("MINIFILES_MAX_UPLOADS", 1),
            ("MINIFILES_MAX_UPLOAD_BYTES", 0),
            ("MINIFILES_RESERVE_BYTES", 0),
        ):
            if key in os.environ and int(os.environ[key]) < minimum:
                raise RuntimeError(f"Invalid {key}.")
        return cls(
            data_root=Path(os.environ.get("MINIFILES_DATA_ROOT", "/data")),
            config_root=Path(os.environ.get("MINIFILES_CONFIG_ROOT", "/config")),
            username=username,
            password=password,
            origin=origin,
            secure_cookie=parsed.scheme == "https",
            session_seconds=int(os.environ.get("MINIFILES_SESSION_SECONDS", "43200")),
            upload_idle_seconds=int(os.environ.get("MINIFILES_UPLOAD_IDLE_SECONDS", "120")),
            max_uploads=int(os.environ.get("MINIFILES_MAX_UPLOADS", "4")),
            max_upload_bytes=int(os.environ.get("MINIFILES_MAX_UPLOAD_BYTES", "0")),
            reserve_bytes=int(os.environ.get("MINIFILES_RESERVE_BYTES", str(1024 * 1024 * 1024))),
        )
