# Installation

MiniFiles runs with Docker Compose. The public image is `ghcr.io/metalogico/minifiles:latest`, available for AMD64 and ARM64. No registry login is needed.

You need Docker with Compose 2.24.4 or newer and a directory to store your files. Run the commands below on the machine that will host MiniFiles, using a non-root account.

Already running MiniFiles? Follow [Updating](UPGRADING.md) instead.

## 1. Get the configuration

```sh
mkdir minifiles
cd minifiles
curl -fL https://raw.githubusercontent.com/metalogico/minifiles/main/compose.yaml -o compose.yaml
curl -fL https://raw.githubusercontent.com/metalogico/minifiles/main/.env.example -o .env.example
```

If you have already cloned or downloaded the repository, open its root directory and skip this step. Keep using the same directory for the remaining commands.

## 2. Set up storage and credentials

```sh
cp .env.example .env
chmod 600 .env
mkdir -p local-data local-config
chmod 700 local-config
id -u
id -g
```

Edit `.env`:

- Replace both `CHANGE_ME` values with your username and password. Keep the single quotes around them, especially if the password contains `$` or `#`. Choose a password without single quotes, or follow Docker Compose's escaping rules.
- Set `MINIFILES_UID` to the number printed by `id -u`, and `MINIFILES_GID` to the number printed by `id -g`. MiniFiles uses this identity to read and write files.
- Leave `MINIFILES_DATA_PATH=./local-data` to start with an empty folder. To browse an existing disk, set it to the disk's mounted directory instead, for example `/mnt/storage`.

The data and settings directories must exist and be writable by the configured UID/GID. If you use another service account, give it access to these directories. Check an existing disk's permissions before changing anything; do not recursively change ownership or permissions on your collection.

Storage must support hard links and Linux file permissions. Symlinks and nested mounts cannot be upload destinations. Leave enough free space for your uploads plus the reserve, which defaults to 1 GiB.

## 3. Start MiniFiles

```sh
docker compose config --quiet
docker compose pull
docker compose up -d --wait
```

Open **http://127.0.0.1:8090** in a browser on the same machine and sign in with the credentials from `.env`.

This address is local to the host. To open MiniFiles from another computer or over your home network, set up [HTTPS](HTTPS.md) using your reverse proxy or the included Caddy configuration. MiniFiles requires HTTPS outside localhost.

## Stop, restart and update

Stop MiniFiles with `docker compose stop`. Start it again with `docker compose up -d --wait`.

Your files and settings live in the host directories, so they survive container replacement. Keep those directories and `.env`; MiniFiles does not back them up for you. See [Updating](UPGRADING.md) before replacing the image.

## Settings

Most installations only need the credentials, UID/GID and storage path changed. The other values in `.env` can stay at their defaults.

| Variable | Default / purpose |
| --- | --- |
| `MINIFILES_USERNAME`, `MINIFILES_PASSWORD` | Your login credentials; replace both placeholders |
| `MINIFILES_UID`, `MINIFILES_GID` | `1000`, `1000`; set these to the identity that owns your storage |
| `MINIFILES_DATA_PATH` | `./local-data`; your files |
| `MINIFILES_CONFIG_PATH` | `./local-config`; sections and cached statistics |
| `MINIFILES_ORIGIN` | `http://127.0.0.1:8090`; the exact browser address, with no path |
| `MINIFILES_BIND_IP`, `MINIFILES_PORT` | `127.0.0.1`, `8090`; where Docker listens on the host |
| `MINIFILES_IMAGE` | `ghcr.io/metalogico/minifiles:latest`; see [version selection](UPGRADING.md#choose-a-version) |
| `MINIFILES_SESSION_SECONDS` | `43200`; sign-in lasts 12 hours |
| `MINIFILES_UPLOAD_IDLE_SECONDS` | `120`; timeout when an upload stops sending data, not a total time limit |
| `MINIFILES_MAX_UPLOADS` | `4`; concurrent upload reservations across all browser tabs |
| `MINIFILES_MAX_UPLOAD_BYTES` | `0`; no file-size limit. Set a positive value in bytes to add one |
| `MINIFILES_RESERVE_BYTES` | `1073741824`; free space to keep available, in bytes |

After changing `.env`, run `docker compose up -d --wait` to apply it. If you change the port, update `MINIFILES_ORIGIN` to match. HTTPS settings are covered in the [HTTPS guide](HTTPS.md).

Run one MiniFiles instance per data directory. Uploaded files use mode `600` and the configured UID/GID; other services need compatible permissions to read them.

## If it does not start

Check the container state and recent logs:

```sh
docker compose ps
docker compose logs --tail 50
```

- **Missing bind directory:** create the directory named in `.env`. For an external disk, confirm it is mounted at the expected path first.
- **Permission denied:** check that the configured UID/GID can write to both the data and settings directories.
- **Credentials not configured:** replace the `CHANGE_ME` values in `.env`.
- **Port already in use:** choose a free `MINIFILES_PORT` and update `MINIFILES_ORIGIN` with the same port.
- **Origin error at login:** open the exact address in `MINIFILES_ORIGIN`. `localhost` and `127.0.0.1` are different origins.

If you enabled Caddy, include both Compose files in these commands as shown in the [HTTPS guide](HTTPS.md#start-caddy).
