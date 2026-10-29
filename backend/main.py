import asyncio
import errno
import hmac
import os
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from .config import Settings
from .database import Database
from .storage import Volume, parts, upload_parts, valid_name

COOKIE = "minifiles_session"


class Login(BaseModel):
    username: str = Field(max_length=256)
    password: str = Field(max_length=1024)


class Section(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    path: str = Field(max_length=2048)
    color: str = Field(pattern="^(blue|purple|green|yellow|red|slate)$", default="blue")
    create_folder: bool = False


class Upload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(max_length=2048)
    name: str = Field(max_length=255)
    size: int = Field(ge=0)


class Directory(BaseModel):
    path: str = Field(min_length=1, max_length=2048)


@dataclass
class Ticket:
    id: str
    session: str
    path: str
    name: str
    size: int
    parent: tuple
    created: float = field(default_factory=time.monotonic)
    active: bool = False
    cancelled: asyncio.Event = field(default_factory=asyncio.Event)


class SmallRequestLimit:
    """Bound JSON input without buffering or wrapping the binary upload stream."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        binary = scope["path"].startswith("/api/uploads/") and scope["path"].endswith("/content")
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if not binary and received > 16384:
                raise HTTPException(413, "Request too large.")
            return message

        async def headers_send(message):
            if message["type"] == "http.response.start":
                message["headers"] += [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"same-origin"),
                    (
                        b"content-security-policy",
                        b"default-src 'self'; script-src 'self'; "
                        b"style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                        b"connect-src 'self'; object-src 'none'; base-uri 'none'; "
                        b"frame-ancestors 'none'",
                    ),
                ]
                if scope["path"].startswith("/api"):
                    message["headers"].append((b"cache-control", b"no-store"))
            await send(message)

        await self.app(scope, bounded_receive, headers_send)


def create_app(settings: Settings | None = None):
    config = settings or Settings.from_env()
    sessions: dict[str, float] = {}
    tickets: dict[str, Ticket] = {}
    reservations: dict[tuple[str, str], str] = {}
    directory_reservations: set[tuple[str, str]] = set()
    capacity_lock = asyncio.Lock()
    login_attempts = defaultdict(deque)
    stats_task = None
    stats_dirty = False
    # Lifespan opens these resources before the first request and closes them on shutdown.
    volume: Volume | None = None
    db: Database | None = None

    def session(request: Request):
        token = request.cookies.get(COOKIE, "")
        if sessions.get(token, 0) <= time.monotonic():
            sessions.pop(token, None)
            raise HTTPException(401, "Your session has expired. Sign in again.")
        return token

    def csrf(request: Request):
        if (
            request.headers.get("origin") != config.origin
            or request.headers.get("x-minifiles") != "1"
        ):
            raise HTTPException(403, "Request origin not allowed.")

    def release_ticket(ticket):
        if tickets.get(ticket.id) is not ticket:
            return
        tickets.pop(ticket.id)
        if reservations.get((ticket.path, ticket.name)) == ticket.id:
            reservations.pop((ticket.path, ticket.name))
        volume.remove_temp(ticket.id + ".part")

    def cancel_ticket(ticket):
        ticket.cancelled.set()
        if not ticket.active:
            release_ticket(ticket)

    def scan_sections():
        result = {}
        for section in db.sections():
            result[section["id"]] = {
                "path": section["path"],
                **volume.section_size(section["path"]),
            }
        db.save_stats(result)

    async def refresh_section_stats():
        nonlocal stats_dirty
        while stats_dirty:
            stats_dirty = False
            await run_in_threadpool(scan_sections)

    def schedule_stats_scan():
        nonlocal stats_task, stats_dirty
        stats_dirty = True
        if stats_task is None or stats_task.done():
            stats_task = asyncio.create_task(refresh_section_stats())

    async def expire_sessions_and_tickets():
        while True:
            await asyncio.sleep(30)
            now = time.monotonic()
            for ticket in list(tickets.values()):
                if sessions.get(ticket.session, 0) <= now or (
                    not ticket.active and now - ticket.created > config.ticket_seconds
                ):
                    cancel_ticket(ticket)
            for token, expires in list(sessions.items()):
                if expires <= now:
                    sessions.pop(token, None)

    @asynccontextmanager
    async def lifespan(app):
        nonlocal volume, db
        volume = Volume(config.data_root)
        db = Database(config.config_root)
        app.state.volume, app.state.db = volume, db
        app.state.tickets = tickets
        schedule_stats_scan()
        cleanup = asyncio.create_task(expire_sessions_and_tickets())
        try:
            yield
        finally:
            cleanup.cancel()
            await asyncio.gather(cleanup, return_exceptions=True)
            for ticket in list(tickets.values()):
                cancel_ticket(ticket)
            if stats_task:
                await asyncio.gather(stats_task, return_exceptions=True)
            volume.close()

    app = FastAPI(
        title="MiniFiles", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.add_middleware(SmallRequestLimit)

    @app.exception_handler(OSError)
    async def filesystem_error(request, exc):
        if exc.errno == errno.ENOSPC:
            return JSONResponse({"detail": "Disk full."}, status_code=507)
        if exc.errno in (errno.EACCES, errno.EPERM):
            return JSONResponse(
                {"detail": "Insufficient permissions on the drive."}, status_code=403
            )
        if exc.errno == errno.ENOENT:
            return JSONResponse({"detail": "File or folder unavailable."}, status_code=404)
        return JSONResponse(
            {"detail": "The path is inaccessible or a disk error occurred."}, status_code=400
        )

    @app.get("/health")
    async def health():
        await run_in_threadpool(volume.disk)
        return {"status": "ok"}

    @app.post("/api/login", dependencies=[Depends(csrf)])
    async def login(body: Login, response: Response, request: Request):
        address = request.client.host if request.client else "local"
        if address not in login_attempts and len(login_attempts) >= 1024:
            login_attempts.clear()
        attempts = login_attempts[address]
        now = time.monotonic()
        while attempts and attempts[0] < now - 60:
            attempts.popleft()
        if len(attempts) >= 10:
            raise HTTPException(429, "Too many attempts. Try again in a minute.")
        attempts.append(now)
        valid_user = hmac.compare_digest(body.username.encode(), config.username.encode())
        valid_password = hmac.compare_digest(body.password.encode(), config.password.encode())
        if not (valid_user and valid_password):
            raise HTTPException(401, "Incorrect username or password.")
        old_token = request.cookies.get(COOKIE)
        if old_token:
            sessions.pop(old_token, None)
            for ticket in list(tickets.values()):
                if ticket.session == old_token:
                    cancel_ticket(ticket)
        token = secrets.token_urlsafe(32)
        sessions[token] = now + config.session_seconds
        response.set_cookie(
            COOKIE,
            token,
            max_age=config.session_seconds,
            httponly=True,
            secure=config.secure_cookie,
            samesite="strict",
        )
        return {"username": config.username}

    @app.get("/api/session")
    async def current_session(token=Depends(session)):
        return {"username": config.username}

    @app.post("/api/logout", dependencies=[Depends(csrf)])
    async def logout(response: Response, token=Depends(session)):
        sessions.pop(token, None)
        for ticket in list(tickets.values()):
            if ticket.session == token:
                cancel_ticket(ticket)
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.get("/api/files", dependencies=[Depends(session)])
    async def files(path: str = ""):
        return await run_in_threadpool(volume.listing, path)

    @asynccontextmanager
    async def directory_operation(path, create):
        segments = upload_parts(path) if create else parts(path)
        keys = [("/".join(segments[:index]), name) for index, name in enumerate(segments)]
        if any(key in reservations or key in directory_reservations for key in keys):
            raise HTTPException(
                423, "Another transfer is using this path. Try again when it finishes."
            )
        directory_reservations.update(keys)
        try:

            def ensure():
                try:
                    with volume.directory(path, create=create):
                        pass
                except OSError as exc:
                    if exc.errno in (errno.ENOTDIR, errno.ELOOP):
                        raise HTTPException(
                            409, "A file or link already occupies the folder path."
                        ) from exc
                    raise

            await run_in_threadpool(ensure)
            yield
        finally:
            directory_reservations.difference_update(keys)

    @app.post("/api/directories", dependencies=[Depends(session), Depends(csrf)])
    async def create_directory(body: Directory):
        path = "/".join(upload_parts(body.path))
        async with directory_operation(path, True):
            return {"path": path}

    @app.get("/api/sections", dependencies=[Depends(session)])
    async def sections():
        return await run_in_threadpool(db.sections)

    async def save_section(body, section_id):
        path = "/".join(parts(body.path))
        if not body.name.strip():
            raise HTTPException(400, "Enter a section name.")
        async with directory_operation(path, body.create_folder):
            await run_in_threadpool(
                db.save_section,
                {
                    "id": section_id,
                    "name": body.name.strip(),
                    "path": path,
                    "color": body.color,
                    "position": len(await run_in_threadpool(db.sections)),
                },
            )
        schedule_stats_scan()
        return {"id": section_id}

    @app.post("/api/sections", dependencies=[Depends(session), Depends(csrf)])
    async def add_section(body: Section):
        return await save_section(body, secrets.token_hex(8))

    @app.put("/api/sections/{section_id}", dependencies=[Depends(session), Depends(csrf)])
    async def update_section(section_id: str, body: Section):
        if not any(s["id"] == section_id for s in await run_in_threadpool(db.sections)):
            raise HTTPException(404, "Section not found.")
        return await save_section(body, section_id)

    @app.delete("/api/sections/{section_id}", dependencies=[Depends(session), Depends(csrf)])
    async def remove_section(section_id: str):
        await run_in_threadpool(db.remove_section, section_id)
        schedule_stats_scan()
        return {"ok": True}

    @app.get("/api/stats", dependencies=[Depends(session)])
    async def stats():
        cached = await run_in_threadpool(db.cached_stats)
        return {
            **cached,
            "disk": await run_in_threadpool(volume.disk),
            "scanning": stats_task is not None and not stats_task.done(),
        }

    @app.post("/api/stats/refresh", dependencies=[Depends(session), Depends(csrf)])
    async def refresh_stats():
        schedule_stats_scan()
        return {"ok": True}

    @app.post("/api/uploads", dependencies=[Depends(csrf)])
    async def prepare_upload(body: Upload, token=Depends(session)):
        valid_name(body.name)
        segments = upload_parts(body.path + "/" + body.name if body.path else body.name)
        path = "/".join(segments[:-1])
        if config.max_upload_bytes and body.size > config.max_upload_bytes:
            raise HTTPException(413, "The file exceeds the configured size limit.")
        async with capacity_lock:
            if (path, body.name) in reservations or (path, body.name) in directory_reservations:
                raise HTTPException(
                    423, "Another page is uploading this file. Try again when it finishes."
                )
            if len(reservations) >= config.max_uploads:
                raise HTTPException(429, "Too many pending transfers. Try again shortly.")
            ticket_id = secrets.token_hex(16)
            reservations[(path, body.name)] = ticket_id
            try:

                def inspect_destination():
                    with volume.directory(path) as fd:
                        if volume.exists(fd, body.name):
                            raise duplicate()
                        parent = os.fstat(fd)
                        return (parent.st_dev, parent.st_ino), volume.disk()["free"]

                parent, free = await run_in_threadpool(inspect_destination)
                if free < body.size + sum(t.size for t in tickets.values()) + config.reserve_bytes:
                    raise HTTPException(507, "Not enough free space for the temporary file.")
                if sessions.get(token, 0) <= time.monotonic():
                    raise HTTPException(401, "Your session has expired.")
                tickets[ticket_id] = Ticket(ticket_id, token, path, body.name, body.size, parent)
                return {"id": ticket_id}
            except BaseException:
                reservations.pop((path, body.name), None)
                raise

    def duplicate():
        return HTTPException(409, {"kind": "duplicate", "message": "Skipped: file already exists"})

    @app.delete("/api/uploads/{ticket_id}", dependencies=[Depends(csrf)])
    async def cancel_upload(ticket_id: str, token=Depends(session)):
        ticket = tickets.get(ticket_id)
        if ticket and ticket.session == token:
            cancel_ticket(ticket)
        return {"ok": True}

    @app.put("/api/uploads/{ticket_id}/content", dependencies=[Depends(csrf)])
    async def upload_content(ticket_id: str, request: Request, token=Depends(session)):
        ticket = tickets.get(ticket_id)
        if not ticket or ticket.session != token:
            raise HTTPException(404, "Transfer not found.")
        if ticket.active:
            raise HTTPException(409, "The transfer has already started.")
        if time.monotonic() - ticket.created > config.ticket_seconds:
            cancel_ticket(ticket)
            raise HTTPException(410, "The upload reservation has expired. Try again.")
        ticket.active = True
        handle = None
        receive_task = None
        abort_task = asyncio.create_task(ticket.cancelled.wait())
        written = 0
        try:
            length = request.headers.get("content-length")
            if length is not None and (not length.isdigit() or int(length) != ticket.size):
                raise HTTPException(400, "The declared size does not match the file.")

            def open_temp():
                fd = os.open(
                    ticket.id + ".part",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=volume.upload_fd,
                )
                return os.fdopen(fd, "wb", buffering=0)

            handle = await run_in_threadpool(open_temp)
            stream = request.stream().__aiter__()
            while True:
                receive_task = asyncio.create_task(anext(stream))
                done, _ = await asyncio.wait(
                    (receive_task, abort_task),
                    timeout=config.upload_idle_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if abort_task in done:
                    raise HTTPException(409, "Upload cancelled.")
                if receive_task not in done:
                    raise HTTPException(408, "Transfer interrupted: no data received.")
                try:
                    chunk = receive_task.result()
                except StopAsyncIteration:
                    break
                if sessions.get(token, 0) <= time.monotonic():
                    raise HTTPException(401, "Your session expired during the upload.")
                written += len(chunk)
                if written > ticket.size:
                    raise HTTPException(400, "Received more bytes than expected.")

                # The ASGI server applies read backpressure; at most one chunk is queued here.
                # Split writes into bounded 1 MiB views; never copy the entire file.
                def write_chunk():
                    if volume.disk()["free"] < len(chunk) + config.reserve_bytes:
                        raise HTTPException(
                            507, "Not enough free space to preserve the drive reserve."
                        )
                    view = memoryview(chunk)
                    while view:
                        n = handle.write(view[: 1024 * 1024])
                        if not n:
                            raise OSError(errno.EIO, "Incomplete write")
                        view = view[n:]

                async with capacity_lock:
                    await run_in_threadpool(write_chunk)
            if written != ticket.size:
                raise HTTPException(400, "Upload incomplete: the file size does not match.")
            await run_in_threadpool(os.fsync, handle.fileno())
            handle.close()
            handle = None
            # Check cancellation/session on the event loop just before atomic finalization.
            if ticket.cancelled.is_set() or sessions.get(token, 0) <= time.monotonic():
                raise HTTPException(409, "Upload cancelled or session expired.")

            def publish_file():
                with volume.directory(ticket.path) as fd:
                    parent = os.fstat(fd)
                    if (parent.st_dev, parent.st_ino) != ticket.parent:
                        raise HTTPException(409, "The destination folder has changed.")
                    if volume.exists(fd, ticket.name):
                        raise duplicate()
                    if ticket.cancelled.is_set():
                        raise HTTPException(409, "Upload cancelled.")
                    try:
                        os.link(
                            ticket.id + ".part",
                            ticket.name,
                            src_dir_fd=volume.upload_fd,
                            dst_dir_fd=fd,
                            follow_symlinks=False,
                        )
                    except FileExistsError:
                        # Classify the new entry without ever replacing it.
                        if volume.exists(fd, ticket.name):
                            raise duplicate()
                        raise HTTPException(409, "The destination changed during publication.")
                    os.unlink(ticket.id + ".part", dir_fd=volume.upload_fd)
                    os.fsync(fd)

            await run_in_threadpool(publish_file)
            return {"ok": True, "bytes": written}
        except ClientDisconnect:
            raise HTTPException(400, "Transfer interrupted by the browser.")
        finally:
            abort_task.cancel()
            if receive_task and not receive_task.done():
                receive_task.cancel()
            await asyncio.gather(
                abort_task, *([receive_task] if receive_task else []), return_exceptions=True
            )
            if handle:
                handle.close()
            release_ticket(ticket)

    if config.frontend.is_dir():
        app.mount("/", StaticFiles(directory=config.frontend, html=True), name="frontend")
    return app
