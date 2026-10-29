"""Check MiniFiles locally in disposable HTTP or HTTPS installations."""

import argparse
import http.cookiejar
import json
import os
import shutil
import socket
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--https", action="store_true", help="Include the official Caddy proxy")
parser.add_argument(
    "--previous-proxy-image", help="Start with this image, then migrate to official Caddy"
)
args = parser.parse_args()
if args.previous_proxy_image and not args.https:
    parser.error("--previous-proxy-image requires --https")


def run(command, **kwargs):
    return subprocess.check_output(command, text=True, **kwargs).strip()


with tempfile.TemporaryDirectory(prefix="minifiles-install-") as directory:
    work = Path(directory)
    shutil.copyfile(ROOT / "compose.yaml", work / "compose.yaml")
    if args.https:
        shutil.copyfile(ROOT / "compose.https.yaml", work / "compose.https.yaml")
        (work / "docker").mkdir()
        shutil.copyfile(ROOT / "docker/Caddyfile", work / "docker/Caddyfile")
    for name in ("local-data", "local-config", "tls-data"):
        (work / name).mkdir(mode=0o700)
    environment = dict(os.environ)
    for key in list(environment):
        if key.startswith(("COMPOSE_", "MINIFILES_")):
            environment.pop(key)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    origin = f"{'https' if args.https else 'http'}://127.0.0.1:{port}"
    values = {
        "MINIFILES_IMAGE": "minifiles:ci",
        "MINIFILES_USERNAME": "local-check",
        "MINIFILES_PASSWORD": "only-for-disposable-check-42",
        "MINIFILES_ORIGIN": origin,
        "MINIFILES_TLS_HOST": "127.0.0.1",
        "MINIFILES_PORT": str(port),
        "MINIFILES_UID": str(os.getuid()),
        "MINIFILES_GID": str(os.getgid()),
    }
    (work / ".env").write_text("".join(f"{key}='{value}'\n" for key, value in values.items()))
    (work / ".env").chmod(0o600)
    command = [
        "docker",
        "compose",
        "--project-directory",
        str(work),
        "--env-file",
        str(work / ".env"),
        "-p",
        f"minifiles-check-{uuid.uuid4().hex[:10]}",
        "-f",
        str(work / "compose.yaml"),
    ]
    if args.https:
        command += ["-f", str(work / "compose.https.yaml")]
    previous = []
    if args.previous_proxy_image:
        override = work / "previous-proxy.json"
        override.write_text(
            json.dumps({"services": {"https": {"image": args.previous_proxy_image}}})
        )
        previous = ["-f", str(override)]

    def compose(*arguments):
        return run(command + list(arguments), env=environment)

    def client():
        context = ssl.create_default_context()
        if args.https:
            certificate = work / "tls-data/caddy/pki/authorities/local/root.crt"
            for _ in range(30):
                if certificate.exists():
                    break
                time.sleep(1)
            context.load_verify_locations(cafile=str(certificate))
        return urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        )

    def request(opener, path, data=None, request_origin=None):
        headers = {"Origin": request_origin or origin, "X-Minifiles": "1"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        return opener.open(
            urllib.request.Request(
                origin + path,
                data=None if data is None else json.dumps(data).encode(),
                headers=headers,
            ),
            timeout=10,
        )

    def login(opener):
        credentials = {
            "username": values["MINIFILES_USERNAME"],
            "password": values["MINIFILES_PASSWORD"],
        }
        for attempt in range(30):
            try:
                with request(opener, "/health") as response:
                    assert json.load(response) == {"status": "ok"}
                break
            except urllib.error.URLError:
                if attempt == 29:
                    raise
                time.sleep(1)
        with request(opener, "/") as response:
            assert response.status == 200
        with request(opener, "/api/login", credentials) as response:
            cookie = response.headers["Set-Cookie"].lower()
            assert "httponly" in cookie and "samesite=strict" in cookie
            assert ("; secure" in cookie) == args.https
        try:
            request(opener, "/api/login", credentials, "https://wrong-origin.invalid")
        except urllib.error.HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError("A foreign origin was accepted")

    try:
        config = json.loads(compose("config", "--format", "json"))
        services = config["services"]
        assert set(services) == ({"minifiles", "https"} if args.https else {"minifiles"})
        if args.https:
            assert not services["minifiles"].get("ports")
            assert services["https"]["image"].startswith("caddy:")
            compose("pull", "https")
        run(
            command + previous + ["up", "-d", "--wait", "--wait-timeout", "180", "--pull", "never"],
            env=environment,
        )
        opener = client()
        login(opener)
        with request(
            opener,
            "/api/sections",
            {"name": "Keep", "path": "Keep", "color": "blue", "create_folder": True},
        ):
            pass
        compose(
            "exec",
            "-T",
            "minifiles",
            "python",
            "-c",
            'from pathlib import Path; Path("/data/Keep/check.txt").write_text("keep")',
        )
        if args.https:
            certificate = (work / "tls-data/caddy/pki/authorities/local/root.crt").read_bytes()
        compose("stop")
        compose(
            "up", "-d", "--force-recreate", "--wait", "--wait-timeout", "180", "--pull", "never"
        )
        # Keep the original trusted CA in this client, including when changing proxy image.
        login(opener)
        with request(opener, "/api/sections") as response:
            assert json.load(response)[0]["name"] == "Keep"
        compose(
            "exec",
            "-T",
            "minifiles",
            "python",
            "-c",
            'from pathlib import Path; assert Path("/data/Keep/check.txt").read_text() == "keep"',
        )
        if args.https:
            assert (
                certificate == (work / "tls-data/caddy/pki/authorities/local/root.crt").read_bytes()
            )
        print("Installation, login, origin checks and data persistence: passed.")
    except Exception:
        print(compose("logs", "--tail", "60"))
        raise
    finally:
        # Only this script's random project and disposable state are removed.
        compose("down", "--volumes", "--remove-orphans")
