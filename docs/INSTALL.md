# Installation

MiniFiles uses published GHCR images with Docker Compose. Download the versioned installation bundle using the [README](../README.md#install-with-docker-compose), then run these commands from its extracted directory. Docker Compose 2.24.4 or newer is required.

## Prepare the host

- Use a local filesystem with hard-link support and Linux ownership/permissions. Uploads are published through a hard link on the data filesystem. Nested mounts and symlinks are not upload destinations.
- Allow enough disk space for the uploaded files plus the configured reserve (1 GiB by default). Temporary uploads live on the data disk, not in the container's writable layer.
- Choose one numeric UID/GID that can write to the data root, settings directory and TLS directory. MiniFiles runs without root and does not change host ownership automatically.
- Reserve an available TCP port, 8090 by default. Only the HTTPS proxy publishes a port.

```sh
cp .env.example .env
chmod 600 .env
mkdir -p local-data local-config tls-data
chmod 700 local-config tls-data
id -u
id -g
```

Edit `.env` and put the last two numbers in `MINIFILES_UID` and `MINIFILES_GID`. If you are logged in as root, choose a non-root service identity instead of UID 0. Replace both credential placeholders. Single-quote passwords containing `$` or `#` so Compose treats those characters literally; use a password without single quotes or follow Compose's escaping rules.

For a new installation under a different service account, create only the new settings/TLS directories with that account's ownership. For an existing data disk, inspect its mount and permissions first. Do not recursively change an existing collection's ownership or permissions. Uploaded files are owned by the configured service UID/GID with mode `600`, so another service needs a compatible identity to read them.

Set `MINIFILES_DATA_PATH` to the actual mounted data directory. The default `./local-data` is an empty local installation. Compose deliberately refuses missing bind paths rather than silently creating a directory on the wrong disk.

## LAN access

The defaults bind to `127.0.0.1`, making MiniFiles accessible only from the server itself. For another computer on your private network, set all address values together. For example, if you control the hostname `files.home.arpa` and it resolves to your server:

```dotenv
MINIFILES_ORIGIN=https://files.home.arpa:8090
MINIFILES_TLS_HOST=files.home.arpa
MINIFILES_BIND_IP=0.0.0.0
MINIFILES_PORT=8090
```

`0.0.0.0` listens on all IPv4 interfaces; use the server's specific LAN IP instead when appropriate. You can also use the server's IP as both `TLS_HOST` and the host in `ORIGIN`. The browser must use that exact HTTPS origin, including a non-default port. The TLS host contains only a hostname/IP, without scheme, port or path. Use a hostname or IPv4 address with the supplied Compose port mapping.

The supplied Caddy configuration uses its own local CA, including for DNS hostnames. It does not obtain a public certificate. Keep the service on a trusted LAN or private network; public internet exposure is outside the supplied deployment configuration.

## Pull and start

```sh
docker compose config --quiet
docker compose pull
docker compose up -d --wait
docker compose ps
```

`config --quiet` checks interpolation without printing credentials. It does not check host permissions, TLS trust or application startup. `pull` downloads the published application and HTTPS proxy; both must use the same release version. The Caddy configuration is included in the proxy image. The runtime uses a single Uvicorn worker, a read-only application filesystem and writable bind mounts for persistent state.

The app's Docker health check calls `/health`; Compose starts the proxy after the backend is healthy. The proxy has no Docker health check, so also verify HTTPS as below. If startup fails, inspect only this stack with `docker compose logs --tail=50`. Missing paths, incorrect ownership, an existing instance on the data volume, insufficient private-directory permissions and unchanged password placeholders prevent startup.

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
docker compose up -d --force-recreate --wait
```

## Configuration reference

| Variable | Default / meaning |
| --- | --- |
| `MINIFILES_USERNAME`, `MINIFILES_PASSWORD` | Required single account; no usable defaults |
| `MINIFILES_ORIGIN` | Required exact web origin; HTTPS outside loopback development |
| `MINIFILES_TLS_HOST` | `127.0.0.1`; certificate hostname/IP |
| `MINIFILES_BIND_IP`, `MINIFILES_PORT` | `127.0.0.1`, `8090`; host listener |
| `MINIFILES_UID`, `MINIFILES_GID` | `1000`, `1000`; numeric process identity |
| `MINIFILES_IMAGE`, `MINIFILES_HTTPS_IMAGE` | Pinned GHCR app and proxy image references |
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
