# MiniFiles

A small, self-hosted file browser for a home server. Browse a mounted drive, organise folder shortcuts, and upload files from a desktop browser. MiniFiles runs in Docker and writes uploads directly to the disk you mount.

[Project website](https://minifiles.metalogico.dev) · [Installation](docs/INSTALL.md) · [Backup and restore](docs/BACKUPS.md) · [Development](docs/DEVELOPMENT.md)

![MiniFiles website showing its animated file browser demo](docs/images/minifiles.png)

The image is the original capture supplied by Sites for the project website. The website demo uses sample files; it is not connected to a live drive.

## Features

- Browse folders with breadcrumbs, grid and list views, and search within the current folder.
- Add, edit and remove coloured folder shortcuts in Settings. Optionally create missing folders when adding a section.
- Upload individual files or whole folder trees through the picker or drag and drop. Paste files from the clipboard.
- Keep each upload's destination while navigating or opening Settings.
- Transfer one file at a time per page, with progress, finalisation status, errors and queue totals.
- Skip existing files automatically. MiniFiles never overwrites files; existing folders are reused.
- Cancel individual items, or finish the current file and discard the remaining queue.
- View filesystem disk usage and section sizes, refreshed at startup, at the end of a queue, or manually.
- Sign in with one configured account, protected by an HTTPS session cookie.
- Stream large uploads to disk without loading the entire file into application memory. The upload path has previously been verified with real 20 GiB files.

The interface is in English and designed for desktop screens at least 1100 px wide. Names you give files and sections are preserved. Download, preview, rename, move and delete operations are outside this version's scope. Interrupted uploads restart from the beginning.

## Install with Docker Compose

Docker downloads the prebuilt GHCR images for Linux AMD64 or ARM64. No Git, PHP, Python, Composer or Node installation is required on the server. Docker Compose 2.24.4 or newer is required.

The workflow publishes images when code reaches `main`. Wait for **Publish Docker images** to succeed and for the GHCR packages to be public before installing. `latest` follows main; `sha-<full commit>` selects a specific build.

Download the installation files from main. The archive also contains the source, but installation does not compile it:

```sh
mkdir minifiles
cd minifiles
curl -fL "https://github.com/metalogico/minifiles/archive/refs/heads/main.tar.gz" -o source.tar.gz
tar -xzf source.tar.gz --strip-components=1
```

For an existing installation, follow [the transition guide](docs/UPGRADING.md) instead of copying a new `.env`. Run the following commands in the extracted directory.

```sh
cp .env.example .env
chmod 600 .env
mkdir -p local-data local-config tls-data
```

Edit `.env` before starting:

1. Replace `MINIFILES_USERNAME` and `MINIFILES_PASSWORD` with your own credentials.
2. Set `MINIFILES_UID` and `MINIFILES_GID` to an identity that can write to all three directories. On Linux, `id -u` and `id -g` show your current identity. Make the new settings and TLS directories private with `chmod 700 local-config tls-data`.
3. For an existing drive, set `MINIFILES_DATA_PATH` to its mounted path and verify its permissions. Do not change an existing collection's ownership or permissions recursively.
4. Keep the loopback address for local use, or set the host, bind address and exact HTTPS origin for LAN access as described in the [installation guide](docs/INSTALL.md#lan-access).

```sh
docker compose config --quiet
docker compose pull
docker compose up -d --wait
```

The app and HTTPS proxy must use the same build. For controlled updates, pin both image references to the same `sha-<full commit>` tag.

With the example address, open `https://127.0.0.1:8090`. Caddy creates a local certificate authority on first startup. Export **only** `tls-data/caddy/pki/authorities/local/root.crt` and trust that public CA certificate on your client before signing in. Keep `root.key` and all other private TLS state on the server. See [HTTPS setup](docs/INSTALL.md#https-and-client-trust) for verification and troubleshooting.

The backend has no published host port. The HTTPS proxy is the only entry point. Keep MiniFiles on your LAN or a trusted private network.

## Use

Open **Drive** to browse the mounted root. Use **Settings** to add shortcuts such as `Books` or `Media/Photos`; paths are relative to the mounted drive. Removing a shortcut leaves its folder and files in place.

Choose files, choose a folder, or drop them into the upload area. For example, selecting `Holiday/Photos/beach.jpg` while browsing `Uploads` creates `Uploads/Holiday/Photos/beach.jpg`. Use drag and drop to include empty folders: the browser's folder picker only exposes files and their relative paths.

Successful entries leave the queue automatically, while totals, errors and skipped duplicates remain visible. `100%` means the bytes have been sent; **Saving to disk…** lasts until the server confirms publication. Keep the page open until the queue finishes. Signing out, reloading or closing the page clears the queue and interrupts unfinished transfers.

**Cancel queue** discards waiting items and lets a file already being sent finish. The X on an individual item interrupts that item. Neither action removes completed files or directories already created.

macOS metadata named `.DS_Store` (case insensitive) or beginning with `._` is excluded at any depth. Other hidden files remain uploadable.

## Data and updates

| Host path from `.env` | Container path | Contents |
| --- | --- | --- |
| `MINIFILES_DATA_PATH` | `/data` | Your files and private `.minifiles/uploads` temporary area |
| `MINIFILES_CONFIG_PATH` | `/config` | SQLite sections and statistics cache |
| `MINIFILES_TLS_PATH` | `/data` in the HTTPS proxy | Persistent CA, certificates and private keys |
| `.env` | Environment variables | Account credentials and deployment settings |

These bind mounts survive container recreation. Sessions are held in memory, so restarting requires signing in again. Back up configuration, TLS state and the mounted files according to the [backup guide](docs/BACKUPS.md); the optional configuration companion does not copy your media.

For updates, let uploads finish, back up settings, TLS state and media as appropriate, then follow [UPGRADING.md](docs/UPGRADING.md). Keep the same `.env`, UID/GID and persistent paths. Released schema changes use incremental migrations; a downgrade may require restoring a matching backup.

## Implementation and limits

FastAPI and Uvicorn serve the API and compiled Vue 3 frontend from one origin. Settings use SQLite from Python's standard library. The frontend uses TypeScript, Vite and Tailwind CSS. The multi-stage Dockerfile keeps Node out of the runtime image.

Run exactly one application worker and one MiniFiles instance per data root. Directory descriptors and no-follow checks confine paths; atomic hard-link publication refuses occupied names. The data mount is writable: API restrictions do not make files immutable against a compromised application process. Space reservations also cannot prevent another program from filling the disk. Uploaded files use mode `600` and the configured UID/GID, which matters when other services need to read them.

Development commands, the verification record and image provenance are in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md), [docs/PUBLIC_RELEASE.md](docs/PUBLIC_RELEASE.md) and [docs/images/README.md](docs/images/README.md).

## License

[MIT](LICENSE).

## Releases and source builds

See [RELEASING.md](docs/RELEASING.md) for local checks, GHCR publication and schema policy. For local Docker builds, use `docker compose -f compose.yaml -f compose.build.yaml up -d --build --wait` from a source checkout with a separate development environment and data. See the same guide before adding optional backup overrides to a source build.
