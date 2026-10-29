# Installation

MiniFiles uses one published GHCR application image with Docker Compose. Download `compose.yaml` and `.env.example` using the [README](../README.md#install-with-docker-compose), then run these commands from that installation directory. Docker Compose 2.24.4 or newer is required.

## Prepare the host

- Use a local filesystem with hard-link support and Linux ownership/permissions. Uploads are published through a hard link on the data filesystem. Nested mounts and symlinks are not upload destinations.
- Allow enough disk space for the uploaded files plus the configured reserve (1 GiB by default). Temporary uploads live on the data disk, not in the container's writable layer.
- Choose one numeric UID/GID that can write to the data root, settings directory (and TLS directory when using optional Caddy). MiniFiles runs without root and does not change host ownership automatically.
- Reserve an available TCP port, 8090 by default. The base stack publishes HTTP on loopback; the HTTPS override replaces that listener with Caddy.

```sh
cp .env.example .env
chmod 600 .env
mkdir -p local-data local-config
chmod 700 local-config
id -u
id -g
```

Edit `.env` and put the last two numbers in `MINIFILES_UID` and `MINIFILES_GID`. If you are logged in as root, choose a non-root service identity instead of UID 0. Replace both credential placeholders. Single-quote passwords containing `$` or `#` so Compose treats those characters literally; use a password without single quotes or follow Compose's escaping rules.

For a new installation under a different service account, create only the new settings/TLS directories with that account's ownership. For an existing data disk, inspect its mount and permissions first. Do not recursively change an existing collection's ownership or permissions. Uploaded files are owned by the configured service UID/GID with mode `600`, so another service needs a compatible identity to read them.

Set `MINIFILES_DATA_PATH` to the actual mounted data directory. The default `./local-data` is an empty local installation. Compose deliberately refuses missing bind paths rather than silently creating a directory on the wrong disk.

## Local start

The base `.env.example` uses `MINIFILES_ORIGIN=http://127.0.0.1:8090`. This HTTP setup is only for the server itself. MiniFiles requires an HTTPS origin for use outside loopback.

```sh
docker compose config --quiet
docker compose pull
docker compose up -d --wait
docker compose ps
```

Open `http://127.0.0.1:8090`. Only the MiniFiles image is downloaded. The app health check calls `/health`; configuration, streaming uploads and the one-worker model are unchanged.

## Use an existing reverse proxy

Keep `MINIFILES_BIND_IP=127.0.0.1` when the reverse proxy runs on the host. Set `MINIFILES_ORIGIN` to the exact browser-facing HTTPS origin, for example `https://files.home.arpa`. Forward all paths to `http://127.0.0.1:8090`, preserving the Host and Origin headers. Recreate MiniFiles after editing `.env`.

If the proxy runs in another container, its localhost is not the Docker host. Connect it and MiniFiles to a shared Docker network with an override and use `minifiles:8000` as the upstream; remove the host port with `ports: !reset []` if it is not needed. Do not expose the plain HTTP listener on an untrusted network. Configure the proxy for streaming request bodies, sufficient upload limits and timeouts for large files. TLS and certificate backups belong to that proxy.

For an existing Caddy installation, the relevant upstream directive is:

```caddyfile
files.home.arpa {
    tls internal
    reverse_proxy 127.0.0.1:8090
}
```

This example assumes Caddy runs on the same host and uses a local CA; keep your existing certificate configuration when appropriate. Do not add the MiniFiles HTTPS override when using your own proxy.

## Optional Caddy HTTPS

`compose.https.yaml` adds the official, digest-pinned `caddy` image. There is no custom MiniFiles proxy image. Caddy runs with the configured non-root UID/GID, a read-only root filesystem and only `NET_BIND_SERVICE` in its capability bounding set, which the official binary's file capability requires. It reads `docker/Caddyfile` through a read-only bind and keeps its existing CA under `MINIFILES_TLS_PATH`.

Download the optional HTTPS configuration into the same installation directory and create a private TLS directory owned by the service identity:

```sh
curl -fL https://raw.githubusercontent.com/metalogico/minifiles/main/compose.https.yaml -o compose.https.yaml
mkdir -p docker tls-data
curl -fL https://raw.githubusercontent.com/metalogico/minifiles/main/docker/Caddyfile -o docker/Caddyfile
chmod 700 tls-data
```

For local HTTPS, set `MINIFILES_ORIGIN=https://127.0.0.1:8090`. For LAN access, use a hostname that resolves to your server or its IPv4 address, and set these values together:

```dotenv
MINIFILES_ORIGIN=https://files.home.arpa:8090
MINIFILES_TLS_HOST=files.home.arpa
MINIFILES_BIND_IP=0.0.0.0
MINIFILES_PORT=8090
```

The TLS host has no scheme, port or path; the origin is the exact browser URL including the non-default port. Use a specific LAN bind address instead of `0.0.0.0` when appropriate. The supplied configuration uses a local CA, not a public certificate.

```sh
docker compose -f compose.yaml -f compose.https.yaml config --quiet
docker compose -f compose.yaml -f compose.https.yaml pull
docker compose -f compose.yaml -f compose.https.yaml up -d --wait
```

**Keep both `-f` options for every subsequent command**, including updates and backups. The merged configuration publishes only Caddy's HTTPS port; the application's HTTP port is removed. The proxy starts after the app is healthy; verify its HTTPS response as described below. `config --quiet` validates configuration without printing credentials, but does not verify host permissions or TLS trust.

## HTTPS and client trust

On first startup Caddy creates the CA and certificate in `MINIFILES_TLS_PATH`. With the default path, the **public** CA certificate is:

```text
tls-data/caddy/pki/authorities/local/root.crt
```

Copy only that certificate to each client and use the operating system/browser's certificate settings to trust it as a CA. On macOS this is Keychain Access; on Windows use the Trusted Root Certification Authorities store. On Linux use the distribution's CA installation procedure. Some browsers maintain a separate certificate store and need their own import. Verify the certificate's fingerprint through your trusted server connection before trusting it.

Keep `root.key`, `intermediate.key` and the rest of `tls-data` private on the server. Never send the CA's private key to clients. Keep the same TLS directory across updates so existing clients continue to recognise the CA.

You can check the service without modifying a system trust store:

```sh
curl --cacert tls-data/caddy/pki/authorities/local/root.crt https://127.0.0.1:8090/health
```

Use your configured hostname/IP and port in that URL. Expected result: `{"status":"ok"}`. Do not use `curl -k` as a substitute for certificate verification. Open the same URL without `/health` to sign in after installing client trust.

A certificate error usually means the client does not trust the CA, the browser's hostname differs from `MINIFILES_TLS_HOST`, or an old certificate/CA was retained by the client. An origin error at login means `MINIFILES_ORIGIN` differs from the address in the browser. Restart after editing `.env`:

```sh
docker compose -f compose.yaml -f compose.https.yaml up -d --force-recreate --wait
```

## Configuration reference

| Variable | Default / meaning |
| --- | --- |
| `MINIFILES_USERNAME`, `MINIFILES_PASSWORD` | Required single account; no usable defaults |
| `MINIFILES_ORIGIN` | Required exact web origin; HTTPS outside loopback development |
| `MINIFILES_TLS_HOST` | `127.0.0.1`; certificate hostname/IP |
| `MINIFILES_BIND_IP`, `MINIFILES_PORT` | `127.0.0.1`, `8090`; host listener |
| `MINIFILES_UID`, `MINIFILES_GID` | `1000`, `1000`; numeric process identity |
| `MINIFILES_IMAGE` | GHCR application reference: latest or sha-COMMIT; Caddy is pinned separately in its override |
| `MINIFILES_DATA_PATH` | `./local-data`; mounted at `/data` in the app |
| `MINIFILES_CONFIG_PATH` | `./local-config`; mounted at `/config` |
| `MINIFILES_TLS_PATH` | `./tls-data`; mounted at `/data` in the proxy |
| `MINIFILES_SESSION_SECONDS` | `43200`; absolute session lifetime (12 hours) |
| `MINIFILES_UPLOAD_IDLE_SECONDS` | `120`; idle receive timeout, not total transfer duration |
| `MINIFILES_MAX_UPLOADS` | `4`; reservations across all pages |
| `MINIFILES_MAX_UPLOAD_BYTES` | `0`; unlimited by the app; positive values set a byte limit |
| `MINIFILES_RESERVE_BYTES` | `1073741824`; free-space margin (1 GiB) |

Do not increase the worker count or scale the app service. The exclusive data-root lock prevents a second instance; sessions and reservations belong to one process.

## Updates and recovery

Let uploads finish and make the backups described in [BACKUPS.md](BACKUPS.md). Follow [UPGRADING.md](UPGRADING.md) for version selection, container replacement and the first transition from source builds. Keep the same `.env`, data/settings/TLS paths and numeric identity. Verify the CA, sign in and check sections/files after the update.

Stop the stack while preserving data with `docker compose stop`. Do not delete bind directories during an update. Source builds use the separate `compose.build.yaml` override described in [RELEASING.md](RELEASING.md).
