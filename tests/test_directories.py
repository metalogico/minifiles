import asyncio
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app

ORIGIN = {"Origin": "http://testserver", "X-MiniFiles": "1"}


@pytest.fixture
def app(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    settings = Settings(
        data,
        tmp_path / "config",
        "test",
        "test-only-password",
        "http://testserver",
        reserve_bytes=0,
    )
    return create_app(settings), data


def login(client):
    return client.post("/api/login", json={"username": "test", "password": "test-only-password"})


def test_directory_upload_tree_preserves_existing_data_and_duplicate_confirmation(app):
    application, data = app
    with TestClient(application, headers=ORIGIN) as client:
        login(client)
        assert (
            client.post("/api/directories", json={"path": "Downloads/Album/Foto"}).status_code
            == 200
        )
        assert (
            client.post("/api/directories", json={"path": "Downloads/Album/Vuota"}).status_code
            == 200
        )
        target = data / "Downloads/Album/Foto/note.txt"
        target.write_bytes(b"original")
        # Reusing a folder never removes its files.
        assert (
            client.post("/api/directories", json={"path": "Downloads/Album/Foto"}).status_code
            == 200
        )
        assert target.read_bytes() == b"original"
        body = {"path": "Downloads/Album/Foto", "name": "note.txt", "size": 3}
        duplicate = client.post("/api/uploads", json=body)
        assert duplicate.status_code == 409
        assert target.read_bytes() == b"original"
        assert (data / "Downloads/Album/Vuota").is_dir()


@pytest.mark.parametrize(
    "path",
    [
        "../escape",
        "/outside",
        "safe/../../outside",
        ".minifiles/x",
        "a//b",
        "a\\b",
        "safe/../other",
    ],
)
def test_directory_paths_cannot_escape_or_create_partial_unsafe_trees(app, path):
    application, data = app
    with TestClient(application, headers=ORIGIN) as client:
        login(client)
        assert client.post("/api/directories", json={"path": path}).status_code == 400
        assert not (data / "safe").exists()


def test_directory_creation_requires_session_and_origin(app):
    application, _ = app
    with TestClient(application) as client:
        assert client.post("/api/directories", json={"path": "Album"}).status_code == 401
        client.headers.update(ORIGIN)
        login(client)
        assert (
            client.post(
                "/api/directories", json={"path": "Album"}, headers={"Origin": "http://untrusted"}
            ).status_code
            == 403
        )


def test_directory_creation_never_replaces_files_or_follows_links(app, tmp_path):
    application, data = app
    outside = tmp_path / "outside"
    outside.mkdir()
    (data / "link").symlink_to(outside, target_is_directory=True)
    (data / "occupied").write_bytes(b"original")
    with TestClient(application, headers=ORIGIN) as client:
        login(client)
        assert client.post("/api/directories", json={"path": "link/new"}).status_code == 409
        assert not (outside / "new").exists()
        assert client.post("/api/directories", json={"path": "occupied/new"}).status_code == 409
        assert (data / "occupied").read_bytes() == b"original"


def test_directory_cannot_take_the_name_of_a_reserved_file(app):
    application, data = app
    with TestClient(application, headers=ORIGIN) as client:
        login(client)
        client.post("/api/uploads", json={"path": "", "name": "Album", "size": 3})
        assert client.post("/api/directories", json={"path": "Album/Sub"}).status_code == 423
        assert not (data / "Album").exists()


def test_upload_cannot_take_a_directory_name_during_creation(app, monkeypatch):
    application, _ = app

    async def scenario():
        async with application.router.lifespan_context(application):
            volume = application.state.volume
            original = volume.directory
            entered = threading.Event()
            resume = threading.Event()
            from contextlib import contextmanager

            @contextmanager
            def paused(path, create=False):
                if create:
                    entered.set()
                    assert resume.wait(timeout=5)
                with original(path, create=create) as descriptor:
                    yield descriptor

            monkeypatch.setattr(volume, "directory", paused)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(application),
                base_url="http://testserver",
                headers=ORIGIN,
            ) as client:
                await client.post(
                    "/api/login", json={"username": "test", "password": "test-only-password"}
                )
                creating = asyncio.create_task(
                    client.post("/api/directories", json={"path": "Album/Sub"})
                )
                try:
                    assert await asyncio.to_thread(entered.wait, 5)
                    response = await client.post(
                        "/api/uploads", json={"path": "", "name": "Album", "size": 3}
                    )
                    assert response.status_code == 423
                finally:
                    resume.set()
                assert (await creating).status_code == 200

    asyncio.run(scenario())
