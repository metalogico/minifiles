import asyncio
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect

from backend.config import Settings
from backend.main import create_app

ORIGIN = {"Origin": "http://testserver", "X-MiniFiles": "1"}


@pytest.fixture
def cfg(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    return Settings(
        data,
        tmp_path / "config",
        "test-user",
        "test-only-password",
        "http://testserver",
        reserve_bytes=0,
    )


@pytest.fixture
def client(cfg):
    with TestClient(create_app(cfg)) as c:
        c.headers.update(ORIGIN)
        assert (
            c.post(
                "/api/login", json={"username": cfg.username, "password": cfg.password}
            ).status_code
            == 200
        )
        yield c


def prepare(client, name="test.bin", size=3, path="", **extra):
    return client.post("/api/uploads", json={"name": name, "size": size, "path": path, **extra})


def upload(client, ticket, data=b"new"):
    return client.put(f"/api/uploads/{ticket}/content", content=data)


def test_authentication_csrf_and_logout(cfg):
    with TestClient(create_app(cfg)) as c:
        c.headers["Accept-Language"] = "it-IT,it;q=0.9"
        for endpoint in ("session", "files", "sections", "stats"):
            response = c.get("/api/" + endpoint)
            assert response.status_code == 401
            assert response.json()["detail"] == "Your session has expired. Sign in again."
        assert (
            c.post(
                "/api/login", json={"username": cfg.username, "password": cfg.password}
            ).status_code
            == 403
        )
        c.headers.update(ORIGIN)
        rejected = c.post("/api/login", json={"username": cfg.username, "password": "wrong"})
        assert rejected.status_code == 401
        assert rejected.json()["detail"] == "Incorrect username or password."
        response = c.post("/api/login", json={"username": cfg.username, "password": cfg.password})
        assert response.status_code == 200
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "SameSite=strict" in response.headers["set-cookie"]
        assert c.post("/api/stats/refresh", headers={"Origin": "http://evil"}).status_code == 403
        assert c.post("/api/logout").status_code == 200
        assert c.get("/api/files").status_code == 401
        assert prepare(c).status_code == 401


def test_expiry_and_rate_limit(cfg):
    with TestClient(create_app(replace(cfg, session_seconds=0))) as c:
        c.headers.update(ORIGIN)
        c.post("/api/login", json={"username": cfg.username, "password": cfg.password})
        assert c.get("/api/session").status_code == 401
    with TestClient(create_app(cfg)) as c:
        c.headers.update(ORIGIN)
        for _ in range(10):
            assert (
                c.post("/api/login", json={"username": "wrong", "password": "wrong"}).status_code
                == 401
            )
        assert (
            c.post("/api/login", json={"username": "wrong", "password": "wrong"}).status_code == 429
        )


@pytest.mark.parametrize(
    "path", ["../outside", "/tmp", "folder/../../tmp", ".minifiles", "x\\y", "a//b", "."]
)
def test_path_confinement(client, path):
    assert client.get("/api/files", params={"path": path}).status_code == 400
    assert (
        client.post(
            "/api/sections", json={"name": "Test", "path": path, "create_folder": True}
        ).status_code
        == 400
    )


@pytest.mark.parametrize("name", ["../escape", "/escape", "a\\b", ".minifiles", "..", "a\x00b"])
def test_upload_name_confinement(client, name):
    assert prepare(client, name=name).status_code == 400


def test_symlinks_are_blocked(client, cfg, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_bytes(b"private")
    (cfg.data_root / "escape").symlink_to(outside, target_is_directory=True)
    assert client.get("/api/files", params={"path": "escape"}).status_code == 400
    assert prepare(client, path="escape").status_code == 400
    assert prepare(client, name="escape").status_code == 409
    rows = client.get("/api/files").json()["entries"]
    assert rows[0]["kind"] == "blocked"
    assert not any(e["name"] == ".minifiles" for e in rows)
    assert (outside / "secret").read_bytes() == b"private"


def test_section_crud_persistence_and_no_file_deletion(client, cfg):
    body = {"name": "Libri", "path": "Books/Sci-Fi", "create_folder": True}
    response = client.post("/api/sections", json=body)
    section_id = response.json()["id"]
    assert (cfg.data_root / "Books/Sci-Fi").is_dir()
    assert (
        client.put("/api/sections/" + section_id, json={**body, "name": "Romanzi"}).status_code
        == 200
    )
    assert (
        client.get("/api/files", params={"path": "Books"}).json()["entries"][0]["name"] == "Sci-Fi"
    )
    # Read from a separate DB connection, as a restarted process would.
    from backend.database import Database

    assert Database(cfg.config_root).sections()[0]["name"] == "Romanzi"
    assert client.delete("/api/sections/" + section_id).status_code == 200
    assert client.get("/api/sections").json() == []
    assert (cfg.data_root / "Books/Sci-Fi").is_dir()


def test_create_duplicate_rejected_and_concurrency(client, cfg):
    ticket = prepare(client).json()["id"]
    assert prepare(client).status_code == 423
    assert upload(client, ticket).status_code == 200
    file = cfg.data_root / "test.bin"
    before = file.stat()
    for size in (0, 3):
        duplicate = prepare(client, size=size)
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"]["kind"] == "duplicate"
        assert "version" not in duplicate.json()["detail"]
        for value in (None, "", "a" * 64):
            assert prepare(client, size=size, overwrite_version=value).status_code == 422
    assert file.read_bytes() == b"new"
    assert file.stat().st_mtime_ns == before.st_mtime_ns
    assert list((cfg.data_root / ".minifiles/uploads").iterdir()) == []


def test_changed_parent_rejected(client, cfg):
    (cfg.data_root / "A").mkdir()
    ticket = prepare(client, path="A").json()["id"]
    (cfg.data_root / "A").rename(cfg.data_root / "B")
    (cfg.data_root / "A").mkdir()
    assert upload(client, ticket).status_code == 409
    assert not (cfg.data_root / "A/test.bin").exists()


def test_new_file_appearing_during_upload_is_not_overwritten(client, cfg):
    ticket = prepare(client).json()["id"]
    (cfg.data_root / "test.bin").write_bytes(b"another writer")
    assert upload(client, ticket).status_code == 409
    assert (cfg.data_root / "test.bin").read_bytes() == b"another writer"


def test_size_errors_cancel_and_ticket_ownership(client, cfg):
    ticket = prepare(client, size=10).json()["id"]
    assert upload(client, ticket, b"short").status_code == 400
    assert not (cfg.data_root / "test.bin").exists()
    ticket = prepare(client).json()["id"]
    assert client.delete("/api/uploads/" + ticket).status_code == 200
    assert upload(client, ticket).status_code == 404
    ticket = prepare(client).json()["id"]
    other = TestClient(client.app)
    try:
        other.headers.update(ORIGIN)
        other.post("/api/login", json={"username": cfg.username, "password": cfg.password})
        assert upload(other, ticket).status_code == 404
    finally:
        other.close()


def test_space_and_configured_limit(cfg):
    for settings, expected in [
        (replace(cfg, max_upload_bytes=2), 413),
        (replace(cfg, reserve_bytes=10**30), 507),
    ]:
        with TestClient(create_app(settings)) as c:
            c.headers.update(ORIGIN)
            c.post("/api/login", json={"username": cfg.username, "password": cfg.password})
            assert prepare(c).status_code == expected


def test_disconnect_and_active_cancellation_preserve_original(cfg):
    async def scenario():
        app = create_app(cfg)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://testserver", headers=ORIGIN
            ) as c:
                await c.post(
                    "/api/login", json={"username": cfg.username, "password": cfg.password}
                )
                file = cfg.data_root / "test.bin"
                file.write_bytes(b"original")

                async def preflight():
                    body = {"name": "fresh.bin", "size": 10, "path": ""}
                    return (await c.post("/api/uploads", json=body)).json()["id"]

                ticket = await preflight()

                async def disconnected():
                    yield b"half"
                    raise ClientDisconnect()

                assert (
                    await c.put(f"/api/uploads/{ticket}/content", content=disconnected())
                ).status_code == 400
                assert file.read_bytes() == b"original"
                assert list((cfg.data_root / ".minifiles/uploads").iterdir()) == []
                ticket = await preflight()
                receiving = asyncio.Event()

                async def stalled():
                    yield b"half"
                    receiving.set()
                    await asyncio.Event().wait()

                task = asyncio.create_task(
                    c.put(f"/api/uploads/{ticket}/content", content=stalled())
                )
                await asyncio.wait_for(receiving.wait(), timeout=5)
                assert file.read_bytes() == b"original"
                await c.delete("/api/uploads/" + ticket)
                assert (await asyncio.wait_for(task, timeout=5)).status_code == 409
                assert file.read_bytes() == b"original"
                assert list((cfg.data_root / ".minifiles/uploads").iterdir()) == []
                ticket = await preflight()
                receiving.clear()
                task = asyncio.create_task(
                    c.put(f"/api/uploads/{ticket}/content", content=stalled())
                )
                await asyncio.wait_for(receiving.wait(), timeout=5)
                await c.post("/api/logout")
                assert (await asyncio.wait_for(task, timeout=5)).status_code == 409
                assert (await c.get("/api/files")).status_code == 401
                assert file.read_bytes() == b"original"
                assert list((cfg.data_root / ".minifiles/uploads").iterdir()) == []

    asyncio.run(scenario())


def test_startup_cleanup_and_stats_nested_sections(cfg):
    temp = cfg.data_root / ".minifiles/uploads"
    temp.mkdir(parents=True)
    (temp / ("a" * 32 + ".part")).write_bytes(b"abandoned")
    temp.parent.chmod(0o700)
    temp.chmod(0o700)
    (temp / ("a" * 32 + ".part")).chmod(0o600)
    with TestClient(create_app(cfg)) as c:
        c.headers.update(ORIGIN)
        c.post("/api/login", json={"username": cfg.username, "password": cfg.password})
        assert list(temp.iterdir()) == []
        for path in ("Books", "Books/Sub"):
            c.post("/api/sections", json={"name": path, "path": path, "create_folder": True})
        (cfg.data_root / "Books/Sub/file").write_bytes(b"1234567")
        for section in c.app.state.db.sections():
            assert c.app.state.volume.section_size(section["path"]) == {
                "bytes": 7,
                "partial": False,
            }
        stats = c.get("/api/stats").json()
        assert stats["disk"]["total"] > stats["disk"]["free"]
        assert stats["disk"]["used"] != 14


def test_credentials_required(monkeypatch):
    monkeypatch.delenv("MINIFILES_USERNAME", raising=False)
    monkeypatch.delenv("MINIFILES_PASSWORD", raising=False)
    with pytest.raises(RuntimeError):
        Settings.from_env()


@pytest.mark.parametrize(
    "path,name",
    [
        ("", ".DS_Store"),
        ("", ".ds_store"),
        ("", "._photo.jpg"),
        ("", "._"),
        ("Album", "._Album"),
        ("._Album", "photo.jpg"),
        ("Album/.DS_Store", "photo.jpg"),
        ("Album/._sub", "photo.jpg"),
    ],
)
def test_metadata_cannot_reserve_or_upload_a_file(client, cfg, path, name):
    response = prepare(client, name=name, path=path)
    assert response.status_code == 400
    assert response.json()["detail"] == "macOS metadata files are excluded from uploads."
    assert list((cfg.data_root / ".minifiles/uploads").iterdir()) == []
    assert set(p.name for p in cfg.data_root.iterdir()) == {".minifiles"}


@pytest.mark.parametrize(
    "path", [".DS_Store", "._Album", "Album/.DS_Store/sub", "Album/._sub/Photos"]
)
def test_metadata_directory_paths_are_rejected_before_creating_parents(client, cfg, path):
    assert client.post("/api/directories", json={"path": path}).status_code == 400
    assert set(p.name for p in cfg.data_root.iterdir()) == {".minifiles"}


@pytest.mark.parametrize("name", [".gitignore", ".env", ".DS_Store.bak", "photo._small.jpg"])
def test_ordinary_hidden_and_similar_names_remain_uploadable(client, cfg, name):
    ticket = prepare(client, name=name).json()["id"]
    assert upload(client, ticket).status_code == 200
    assert (cfg.data_root / name).read_bytes() == b"new"


def test_metadata_filter_does_not_modify_existing_files(client, cfg):
    for name in [".DS_Store", "._photo.jpg"]:
        target = cfg.data_root / name
        target.write_bytes(b"original")
        assert prepare(client, name=name).status_code == 400
        assert target.read_bytes() == b"original"


def test_uploads_and_directories_do_not_scan_until_an_explicit_refresh(cfg, monkeypatch):
    import time

    from backend.database import Database
    from backend.storage import Volume

    Database(cfg.config_root).save_section(
        {"id": "collection", "name": "Collection", "path": "", "color": "blue", "position": 0}
    )
    original = Volume.section_size
    scans = []

    def measured(self, path):
        scans.append(path)
        return original(self, path)

    monkeypatch.setattr(Volume, "section_size", measured)
    with TestClient(create_app(cfg), headers=ORIGIN) as c:
        c.post("/api/login", json={"username": cfg.username, "password": cfg.password})

        def settled_stats():
            for _ in range(200):
                result = c.get("/api/stats").json()
                if not result["scanning"]:
                    return result
                time.sleep(0.005)
            pytest.fail("Statistics scan did not finish")

        before = settled_stats()
        baseline = len(scans)
        for i in range(3):
            assert c.post("/api/directories", json={"path": f"Album/Sub{i}"}).status_code == 200
            ticket = prepare(c, name=f"file-{i}", path=f"Album/Sub{i}").json()["id"]
            assert upload(c, ticket).status_code == 200
        assert len(scans) == baseline
        assert c.get("/api/stats").json()["sections"] == before["sections"]
        assert c.post("/api/stats/refresh").status_code == 200
        after = settled_stats()
        assert len(scans) == baseline + 1
        assert after["sections"]["collection"]["bytes"] == 9
