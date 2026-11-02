# Updating MiniFiles

Let active uploads finish before updating. Keep your `.env`, storage directories and Compose files. Back up your files and settings with your usual tools; stop MiniFiles before copying `local-config`, including any SQLite WAL/SHM files.

## Choose a version

By default, `MINIFILES_IMAGE=ghcr.io/metalogico/minifiles:latest` follows the published `main` build.

To stay on a specific build, set `MINIFILES_IMAGE=ghcr.io/metalogico/minifiles:sha-COMMIT` in `.env`, replacing `COMMIT` with the full published main commit SHA. You can also pin an image digest. Note your current image reference and digest before changing it, in case you need to go back.

Review any configuration or migration changes for the target version. Compare its Compose files and `.env.example` with your installation, keeping your private values and overrides. If you need the matching source, download `https://github.com/metalogico/minifiles/archive/COMMIT.tar.gz` into a separate directory.

## Update the containers

From your installation directory:

```sh
docker compose config --quiet
docker compose pull
docker compose stop
docker compose up -d --wait
docker compose ps
```

If you use the included Caddy setup, use `docker compose -f compose.yaml -f compose.https.yaml` in place of `docker compose` on every line. Keep any custom `-p`, `--env-file` or `-f` options on every command too.

Pulling happens before stopping, so a failed download leaves the current version running. Container replacement preserves the bind-mounted files and settings. Keep their paths and UID/GID unchanged. Do not delete storage directories, reset the database or prune volumes during an update.

Once the service is healthy, sign in and check your sections and files. Restarting clears existing sessions. If startup fails, stop the stack and check `docker compose logs --tail 50` with the same Compose options.

## Moving from a source build

Remove `compose.build.yaml` from your commands or `COMPOSE_FILE`, and set `MINIFILES_IMAGE` to the published image you want. Keep the same project name, `.env`, storage paths, UID/GID and HTTPS settings.

Older development builds could change the database schema in place. If yours predates the first published image, check compatibility using copies of its data and settings before updating. A different schema may need a specific migration; do not reset SQLite's schema version to force startup.

## Moving from the old custom HTTPS image

Use `compose.yaml` together with `compose.https.yaml` and place the supplied `docker/Caddyfile` in your installation directory. Keep any deliberate local changes to that file.

Keep the existing `MINIFILES_TLS_PATH` and its contents: they contain the CA trusted by your clients. The proxy service is still named `https`, with TLS state mounted at `/data`. The old `MINIFILES_HTTPS_IMAGE` and `MINIFILES_HTTPS_BUILD_IMAGE` variables are no longer used.

If you switch to your own reverse proxy instead, follow [HTTPS and network access](HTTPS.md#use-an-existing-reverse-proxy) and check client trust before retiring the old proxy.

## Rolling back

An older image may not understand a database that has already been migrated. MiniFiles refuses a schema newer than it supports.

Stop MiniFiles, restore matching pre-update settings and files from your backup, and select the previous image. Keep the original credentials and HTTPS CA. Check recovery using copies before replacing the live installation.
