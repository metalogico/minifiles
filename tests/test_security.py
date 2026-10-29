"""Regression tests for the add-only boundary, using disposable volumes only."""

import asyncio
import os
import threading
from contextlib import contextmanager
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.storage import Volume

HEADERS = {"Origin": "http://testserver", "X-MiniFiles": "1"}


@pytest.fixture
def cfg(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    return Settings(
        data,
        tmp_path / "config",
        "test",
        "test-only-password",
        "http://testserver",
        reserve_bytes=0,
    )


def login(c):
    return c.post("/api/login", json={"username": "test", "password": "test-only-password"})


def prepare(c, name="new", size=3):
    return c.post("/api/uploads", json={"path": "", "name": name, "size": size})


@pytest.mark.parametrize(
    "path", [".MINIFILES", ".MiniFiles/uploads", "../outside", "/tmp", "safe/../../escape"]
)
def test_all_path_entrypoints_block_internal_and_traversal(cfg, path):
    with TestClient(create_app(cfg), headers=HEADERS) as c:
        login(c)
        for method, url, body in [
            ("GET", "/api/files?path=" + path, None),
            ("POST", "/api/uploads", {"path": path, "name": "x", "size": 0}),
            ("POST", "/api/directories", {"path": path}),
            ("POST", "/api/sections", {"name": "Test", "path": path, "create_folder": True}),
        ]:
            assert c.request(method, url, json=body).status_code >= 400


@pytest.mark.parametrize("kind", ["file", "directory", "symlink", "fifo"])
def test_new_entry_at_atomic_publication_is_never_replaced(cfg, monkeypatch, kind):
    with TestClient(create_app(cfg), headers=HEADERS) as c:
        login(c)
        ticket = prepare(c).json()["id"]
        target = cfg.data_root / "new"
        original = os.link

        def race(*args, **kwargs):
            if kind == "file":
                target.write_bytes(b"external writer")
            elif kind == "directory":
                target.mkdir()
            elif kind == "symlink":
                target.symlink_to(cfg.config_root)
            else:
                os.mkfifo(target)
            return original(*args, **kwargs)

        monkeypatch.setattr(os, "link", race)
        response = c.put(f"/api/uploads/{ticket}/content", content=b"new")
        assert response.status_code == 409
        assert response.json()["detail"]["kind"] == ("duplicate" if kind == "file" else "conflict")
        if kind == "file":
            assert target.read_bytes() == b"external writer"
        elif kind == "directory":
            assert target.is_dir()
        elif kind == "symlink":
            assert target.is_symlink()
        else:
            assert target.is_fifo()
        assert list((cfg.data_root / ".minifiles/uploads").iterdir()) == []


def test_space_reservations_are_serial_and_released_once(cfg, monkeypatch):
    async def scenario():
        app = create_app(cfg)
        async with app.router.lifespan_context(app):
            monkeypatch.setattr(app.state.volume, "disk", lambda: {"free": 100})
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://testserver", headers=HEADERS
            ) as c:
                await c.post(
                    "/api/login", json={"username": "test", "password": "test-only-password"}
                )
                responses = await asyncio.gather(
                    *[
                        c.post("/api/uploads", json={"path": "", "name": str(i), "size": 60})
                        for i in range(2)
                    ]
                )
                assert sorted(r.status_code for r in responses) == [200, 507]
                ticket = next(r.json()["id"] for r in responses if r.status_code == 200)
                assert sum(t.size for t in app.state.tickets.values()) == 60
                for _ in range(2):
                    assert (await c.delete("/api/uploads/" + ticket)).status_code == 200
                assert not app.state.tickets
                assert (
                    await c.post("/api/uploads", json={"path": "", "name": "retry", "size": 100})
                ).status_code == 200
                await c.post("/api/logout")
                assert not app.state.tickets

    asyncio.run(scenario())


def test_stream_preserves_reserve_and_releases_after_failure(cfg, monkeypatch):
    with TestClient(create_app(replace(cfg, reserve_bytes=10)), headers=HEADERS) as c:
        login(c)
        monkeypatch.setattr(c.app.state.volume, "disk", lambda: {"free": 100})
        ticket = prepare(c).json()["id"]
        monkeypatch.setattr(c.app.state.volume, "disk", lambda: {"free": 12})
        assert c.put(f"/api/uploads/{ticket}/content", content=b"new").status_code == 507
        assert not (cfg.data_root / "new").exists()
        assert not c.app.state.tickets
        assert list((cfg.data_root / ".minifiles/uploads").iterdir()) == []
        monkeypatch.setattr(c.app.state.volume, "disk", lambda: {"free": 100})
        ticket = prepare(c).json()["id"]
        assert c.put(f"/api/uploads/{ticket}/content", content=b"new").status_code == 200


def test_expired_ticket_releases_reservation(cfg):
    with TestClient(create_app(replace(cfg, ticket_seconds=-1)), headers=HEADERS) as c:
        login(c)
        ticket = prepare(c).json()["id"]
        assert c.put(f"/api/uploads/{ticket}/content", content=b"new").status_code == 410
        assert not c.app.state.tickets
        assert prepare(c).status_code == 200


def test_second_instance_cannot_clean_active_uploads(cfg):
    first = Volume(cfg.data_root)
    target = cfg.data_root / ".minifiles/uploads" / ("b" * 32 + ".part")
    target.write_bytes(b"active")
    target.chmod(0o600)
    try:
        with pytest.raises(RuntimeError, match="Another MiniFiles"):
            Volume(cfg.data_root)
        assert target.read_bytes() == b"active"
    finally:
        first.close()
    second = Volume(cfg.data_root)
    try:
        assert not target.exists()
    finally:
        second.close()


@pytest.mark.parametrize("unsafe", ["permissions", "owner", "symlink", "file"])
def test_internal_directory_must_be_private_and_owned(cfg, monkeypatch, unsafe):
    internal = cfg.data_root / ".minifiles"
    if unsafe == "symlink":
        internal.symlink_to(cfg.config_root)
    elif unsafe == "file":
        internal.write_bytes(b"original")
    else:
        internal.mkdir(mode=0o755 if unsafe == "permissions" else 0o700)
    if unsafe == "owner":
        monkeypatch.setattr(os, "geteuid", lambda: internal.stat().st_uid + 1)
    with pytest.raises((RuntimeError, OSError)):
        Volume(cfg.data_root)
    if unsafe == "file":
        assert internal.read_bytes() == b"original"


def test_cleanup_does_not_delete_unrecognised_files(cfg):
    volume = Volume(cfg.data_root)
    volume.close()
    folder = cfg.data_root / ".minifiles/uploads"
    target = folder / ("z" * 32 + ".part")
    target.write_bytes(b"unrecognised")
    volume = Volume(cfg.data_root)
    try:
        assert target.read_bytes() == b"unrecognised"
    finally:
        volume.close()


def test_settings_folder_creation_reserves_names(cfg, monkeypatch):
    async def scenario():
        app = create_app(cfg)
        async with app.router.lifespan_context(app):
            entered = threading.Event()
            resume = threading.Event()
            original = app.state.volume.directory

            @contextmanager
            def paused(path, create=False):
                if create:
                    entered.set()
                    assert resume.wait(5)
                with original(path, create=create) as fd:
                    yield fd

            monkeypatch.setattr(app.state.volume, "directory", paused)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://testserver", headers=HEADERS
            ) as c:
                await c.post(
                    "/api/login", json={"username": "test", "password": "test-only-password"}
                )
                creating = asyncio.create_task(
                    c.post(
                        "/api/sections",
                        json={"name": "Album", "path": "Album/Sub", "create_folder": True},
                    )
                )
                try:
                    assert await asyncio.to_thread(entered.wait, 5)
                    assert (
                        await c.post("/api/uploads", json={"path": "", "name": "Album", "size": 3})
                    ).status_code == 423
                finally:
                    resume.set()
                assert (await creating).status_code == 200

    asyncio.run(scenario())


def test_encoded_query_traversal_is_rejected_without_decoding_json_names(cfg):
    with TestClient(create_app(cfg), headers=HEADERS) as c:
        login(c)
        assert c.get("/api/files?path=%2e%2e%2foutside").status_code == 400
        # JSON names are literal filesystem names, never URL-decoded a second time.
        assert c.post("/api/directories", json={"path": "%2e%2e/outside"}).status_code == 200
        assert (cfg.data_root / "%2e%2e/outside").is_dir()


def test_environment_requires_https_and_secure_cookie(monkeypatch):
    monkeypatch.setenv("MINIFILES_USERNAME", "test")
    monkeypatch.setenv("MINIFILES_PASSWORD", "test-only-password")
    monkeypatch.setenv("MINIFILES_ORIGIN", "http://192.0.2.10:8090")
    with pytest.raises(RuntimeError, match="HTTPS"):
        Settings.from_env()
    monkeypatch.setenv("MINIFILES_ORIGIN", "https://192.0.2.10:8090")
    assert Settings.from_env().secure_cookie
    monkeypatch.setenv("MINIFILES_RESERVE_BYTES", "-1")
    with pytest.raises(RuntimeError, match="MINIFILES_RESERVE_BYTES"):
        Settings.from_env()


def test_https_session_cookie_is_secure(cfg):
    settings = replace(cfg, origin="https://testserver", secure_cookie=True)
    with TestClient(
        create_app(settings),
        base_url="https://testserver",
        headers={**HEADERS, "Origin": "https://testserver"},
    ) as c:
        cookie = login(c).headers["set-cookie"]
        assert all(flag in cookie for flag in ("Secure", "HttpOnly", "SameSite=strict"))
        assert c.get("/api/files").status_code == 200
