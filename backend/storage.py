"""All filesystem access uses directory descriptors; symlinks are never followed."""

import fcntl
import os
import re
import stat
from contextlib import contextmanager

from fastapi import HTTPException

INTERNAL = ".minifiles"
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def parts(path: str) -> list[str]:
    if not path:
        return []
    segments = path.split("/")
    for name in segments:
        valid_name(name)
    return segments


def upload_parts(path: str) -> list[str]:
    segments = parts(path)
    if any(name.lower() == ".ds_store" or name.startswith("._") for name in segments):
        raise HTTPException(400, "macOS metadata files are excluded from uploads.")
    return segments


def valid_name(name: str):
    if (
        name in ("", ".", "..")
        or name.casefold() == INTERNAL
        or "/" in name
        or "\\" in name
        or any(ord(c) < 32 or ord(c) == 127 for c in name)
        or len(name.encode("utf-8")) > 255
    ):
        raise HTTPException(400, "Invalid name or path.")


class Volume:
    def __init__(self, root):
        self.fd = self.internal_fd = self.upload_fd = None
        try:
            self.fd = os.open(root, DIR_FLAGS)
            self.device = os.fstat(self.fd).st_dev
            self.internal_fd = self.private_directory(self.fd, INTERNAL)
            # Hold the directory lock until close; a second worker must fail before cleanup.
            try:
                fcntl.flock(self.internal_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("Another MiniFiles instance owns this volume.") from exc
            self.upload_fd = self.private_directory(self.internal_fd, "uploads")
            self.internal_ids = {
                (os.fstat(fd).st_dev, os.fstat(fd).st_ino)
                for fd in (self.internal_fd, self.upload_fd)
            }
            for name in os.listdir(self.upload_fd):
                if re.fullmatch(r"[0-9a-f]{32}\.part", name):
                    self.remove_temp(name)
        except BaseException:
            self.close()
            raise

    def private_directory(self, parent, name):
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent)
        except FileExistsError:
            pass
        fd = os.open(name, DIR_FLAGS, dir_fd=parent)
        info = os.fstat(fd)
        if (
            info.st_dev != self.device
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            os.close(fd)
            raise RuntimeError(
                "MiniFiles internal directories must be private, owned by the service and on the data filesystem."
            )
        return fd

    def remove_temp(self, name):
        if not re.fullmatch(r"[0-9a-f]{32}\.part", name):
            raise RuntimeError("Invalid temporary filename.")
        try:
            info = os.stat(name, dir_fd=self.upload_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise RuntimeError("Unsafe entry in the MiniFiles upload directory.")
        os.unlink(name, dir_fd=self.upload_fd)

    def close(self):
        for name in ("upload_fd", "internal_fd", "fd"):
            fd = getattr(self, name, None)
            if fd is not None:
                os.close(fd)
                setattr(self, name, None)

    @contextmanager
    def directory(self, path: str, create=False):
        fd = os.dup(self.fd)
        try:
            for name in parts(path):
                if create:
                    try:
                        os.mkdir(name, dir_fd=fd)
                    except FileExistsError:
                        pass
                child = os.open(name, DIR_FLAGS, dir_fd=fd)
                os.close(fd)
                fd = child
                info = os.fstat(fd)
                if (info.st_dev, info.st_ino) in self.internal_ids:
                    raise HTTPException(400, "Internal folders are not accessible.")
                if info.st_dev != self.device:
                    raise HTTPException(400, "The folder is on another filesystem.")
            yield fd
        finally:
            os.close(fd)

    @staticmethod
    def exists(fd, name):
        try:
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        if not stat.S_ISREG(info.st_mode):
            raise HTTPException(
                409,
                {
                    "kind": "conflict",
                    "message": "A folder, link or special file already uses this name.",
                },
            )
        return True

    def listing(self, path):
        entries = []
        with self.directory(path) as fd:
            with os.scandir(fd) as iterator:
                for entry in iterator:
                    if entry.name.casefold() == INTERNAL:
                        continue
                    try:
                        info = entry.stat(follow_symlinks=False)
                        if stat.S_ISDIR(info.st_mode):
                            kind = "directory"
                        elif stat.S_ISREG(info.st_mode):
                            kind = "file"
                        else:
                            kind = "blocked"
                        if info.st_dev != self.device:
                            kind = "blocked"
                        entries.append(
                            {
                                "name": entry.name,
                                "kind": kind,
                                "size": info.st_size if kind == "file" else None,
                                "modified": info.st_mtime,
                            }
                        )
                    except FileNotFoundError:
                        continue
        return {
            "path": path,
            "entries": sorted(
                entries, key=lambda entry: (entry["kind"] != "directory", entry["name"].casefold())
            ),
        }

    def disk(self):
        info = os.fstatvfs(self.fd)
        total = info.f_blocks * info.f_frsize
        free = info.f_bavail * info.f_frsize
        used = (info.f_blocks - info.f_bfree) * info.f_frsize
        return {
            "total": total,
            "used": used,
            "free": free,
            "percent": round(used / total * 100, 1) if total else 0,
        }

    def section_size(self, path):
        errors = 0

        def walk(fd):
            nonlocal errors
            total = 0
            with os.scandir(fd) as entries:
                for entry in entries:
                    if entry.name.casefold() == INTERNAL:
                        continue
                    try:
                        info = entry.stat(follow_symlinks=False)
                        if info.st_dev != self.device:
                            errors += 1
                        elif stat.S_ISREG(info.st_mode):
                            total += info.st_size
                        elif stat.S_ISDIR(info.st_mode):
                            child = os.open(entry.name, DIR_FLAGS, dir_fd=fd)
                            try:
                                total += walk(child)
                            finally:
                                os.close(child)
                    except OSError:
                        errors += 1
            return total

        try:
            with self.directory(path) as fd:
                size = walk(fd)
        except (OSError, HTTPException, RecursionError):
            return {"bytes": 0, "partial": True}
        return {"bytes": size, "partial": errors > 0}
