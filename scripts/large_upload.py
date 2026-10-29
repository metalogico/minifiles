"""Opt-in real-file upload/integrity/RSS benchmark against the local Docker stack.

Creates and later removes only this benchmark's source and uploaded file.
The destination must be the dedicated, disposable test folder, not production.
"""

import argparse
import hashlib
import http.client
import json
import os
import shutil
import ssl
import subprocess
import threading
import time
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gib", type=int, default=20)
    parser.add_argument("--container", required=True)
    parser.add_argument("--env", type=Path, default=Path(".env.local"))
    parser.add_argument("--origin", default="https://127.0.0.1:8090")
    parser.add_argument("--data", type=Path, default=Path("local-data"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/large-upload.json"))
    parser.add_argument(
        "--ca", type=Path, default=Path("tls-data/caddy/pki/authorities/local/root.crt")
    )
    args = parser.parse_args()
    tls = (
        ssl.create_default_context(cafile=str(args.ca))
        if args.origin.startswith("https:")
        else None
    )
    root = Path(__file__).resolve().parents[1]
    work = root / "artifacts/benchmark"
    work.mkdir(parents=True, exist_ok=True)
    size = args.gib * 1024**3
    if shutil.disk_usage(work).free < size * 2 + 5 * 1024**3:
        raise SystemExit("Not enough space for the source and destination files.")
    env = dict(
        line.split("=", 1)
        for line in args.env.read_text().splitlines()
        if line and not line.startswith("#")
    )
    headers = {"Origin": args.origin, "X-MiniFiles": "1", "Content-Type": "application/json"}

    def api(path, body=None):
        request = urllib.request.Request(
            args.origin + "/api" + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
        )
        with urllib.request.urlopen(request, context=tls) as response:
            return json.load(response), response.headers

    _, response_headers = api(
        "/login", {"username": env["MINIFILES_USERNAME"], "password": env["MINIFILES_PASSWORD"]}
    )
    cookie = response_headers["Set-Cookie"].split(";", 1)[0]
    headers["Cookie"] = cookie
    folder = "MiniFiles-benchmark-" + str(time.time_ns())
    section, _ = api(
        "/sections", {"name": "Temporary benchmark", "path": folder, "create_folder": True}
    )
    source = work / "source.bin"
    destination = args.data / folder / "large-test.bin"
    if source.exists():
        raise SystemExit("A benchmark source already exists; check it before retrying.")
    stop = threading.Event()
    rss_samples = []

    def sample():
        while not stop.is_set():
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    args.container,
                    "python",
                    "-c",
                    "from pathlib import Path; "
                    "lines = Path('/proc/1/status').read_text().splitlines(); "
                    "print(next(line.split()[1] for line in lines if line.startswith('VmRSS:')))",
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                try:
                    rss_samples.append(int(result.stdout.strip()) * 1024)
                except ValueError:
                    pass
            stop.wait(0.5)

    digest = hashlib.sha256()
    block = os.urandom(1024 * 1024)
    print(f"Creating the source file: {args.gib} GiB", flush=True)
    try:
        with source.open("xb", buffering=0) as handle:
            for _ in range(size // len(block)):
                handle.write(block)
                digest.update(block)
            os.fsync(handle.fileno())
        expected = digest.hexdigest()
        ticket, _ = api("/uploads", {"path": folder, "name": "large-test.bin", "size": size})
        observer = threading.Thread(target=sample, daemon=True)
        observer.start()
        started = time.monotonic()
        from urllib.parse import urlsplit

        url = urlsplit(args.origin)
        conn = (
            http.client.HTTPSConnection(url.hostname, url.port, timeout=180, context=tls)
            if tls
            else http.client.HTTPConnection(url.hostname, url.port, timeout=180)
        )
        conn.putrequest("PUT", f"/api/uploads/{ticket['id']}/content")
        for name, value in {
            **headers,
            "Content-Type": "application/octet-stream",
            "Content-Length": str(size),
        }.items():
            conn.putheader(name, value)
        conn.endheaders()
        print("Streaming over HTTPS…", flush=True)
        with source.open("rb") as handle:
            sent = 0
            while chunk := handle.read(1024 * 1024):
                conn.send(chunk)
                sent += len(chunk)
                if sent % (5 * 1024**3) == 0:
                    print(f"Sent {sent // 1024**3} GiB", flush=True)
        response = conn.getresponse()
        result = json.loads(response.read())
        assert response.status == 200, result
        elapsed = time.monotonic() - started
        stop.set()
        observer.join(timeout=10)
        actual = hashlib.sha256()
        with destination.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                actual.update(chunk)
        report = {
            "size_bytes": size,
            "destination_size": destination.stat().st_size,
            "source_sha256": expected,
            "destination_sha256": actual.hexdigest(),
            "integrity_passed": expected == actual.hexdigest()
            and destination.stat().st_size == size,
            "seconds": round(elapsed, 2),
            "throughput_mib_s": round(size / elapsed / 1024**2, 2),
            "rss_min_bytes": min(rss_samples) if rss_samples else None,
            "rss_peak_bytes": max(rss_samples) if rss_samples else None,
            "rss_samples": len(rss_samples),
            "runtime": (
                "Docker; Python HTTP client with verified CA when HTTPS is selected; "
                "actual regular source file"
            ),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2), flush=True)
        assert report["integrity_passed"] and rss_samples
    finally:
        stop.set()
        source.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        if destination.parent.is_dir():
            destination.parent.rmdir()
        request = urllib.request.Request(
            args.origin + "/api/sections/" + section["id"], headers=headers, method="DELETE"
        )
        urllib.request.urlopen(request, context=tls).close()


if __name__ == "__main__":
    main()
