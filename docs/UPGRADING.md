# Updates and the first image-based installation

Use `https://github.com/metalogico/minifiles/archive/COMMIT.tar.gz` for a source archive matching a pinned image, replacing COMMIT with the full published main commit SHA.

## Before every update

1. Review the target main commit and migration requirements. Retain the current version/image digest and installation files.
2. Create and verify a [backup](BACKUPS.md); export it off the host. Preserve `.env`, application data and any private TLS state. Never copy a live SQLite file without the documented snapshot procedure.
3. Download the source archive for the target main commit into a **separate directory**. Compare its Compose and example environment with your deployed configuration. Copy approved configuration changes into the existing installation directory; keep your private `.env` and existing override files.
4. Set `MINIFILES_IMAGE=ghcr.io/metalogico/minifiles:sha-COMMIT` in your existing `.env`, replacing COMMIT with the full published main commit SHA. `latest` is also supported, but a pinned commit gives you control over updates. Review new environment variables individually.

Use the same `-p`, `--env-file` and `-f` options on **every** command when your deployment uses them. The abbreviated commands below assume the default files and project name. Let every upload finish before stopping the stack.

```sh
docker compose config --quiet
docker compose pull
docker compose stop
docker compose up -d --wait
docker compose ps
```

Pull before stopping to reduce downtime. If the pull fails, the running version remains available. If startup or a migration fails, stop the stack and inspect this stack's logs; do not restart background services against a failed migration. Successful health checks should be followed by sign-in, checking existing records/files, a small edit/upload and a new backup.

Stopping/recreating containers preserves persistent storage. **Never run `down -v`, `migrate:fresh`, database resets or volume pruning as part of an update.** Updates do not regenerate credentials, keys or the CA.

## Existing source-built installations: first transition to published images

Changing the image is safe only when it uses the same storage and a compatible schema. Older development revisions could change migrations in place. The first release does not infer or repair every historical development schema.

- Record the current Compose project name from container labels, actual volume names and bind mount paths, numeric UID/GID, environment file and override files. `docker compose ps` and `docker inspect <container>` help inspect the installation; avoid sharing their secret-bearing output.
- Compare the deployed database schema and migration history with the v1 baseline using a **restored copy** of a verified backup. Run the candidate image in a separate project with copied data, separate ports and bind directories. Confirm existing records and files, authentication, migrations and backup/restore. A production mount must never be used for this rehearsal.
- If the old schema differs, prepare and test a specific incremental migration/import before updating the real stack. Do not delete rows from Laravel's migrations table or reset SQLite's schema version to force startup.
- Keep the real `.env`, `APP_KEY` where applicable, login values, API credentials and HTTPS CA. Replace only the old local image reference with the GHCR reference. Remove any source-build override from the production command or `COMPOSE_FILE`.
- Preserve all existing data mounts and the exact Compose project name. A different name selects new empty volumes; that does not mean the original data was erased. Keep external backup disks and their identity markers configured.
- Perform the regular update above only after the rehearsal succeeds. Retain the old image and backup until the new installation is verified.

The local smoke script tests a fresh image-only install and persistence across container recreation. GitHub Actions does not run these tests. It does not inspect or migrate a particular home server's historical database.

## Move from the custom HTTPS image to official Caddy

The base Compose now contains only MiniFiles. Existing HTTPS installations must explicitly include `-f compose.yaml -f compose.https.yaml` on every command, including the initial pull and recreation. Keep the same Compose project name, `.env`, HTTPS origin, bind address, port, UID/GID and absolute data/settings/TLS paths. If using the scheduled backup companion, include `-f compose.backup.yaml` too.

The service remains named `https`, and the TLS mount inside Caddy remains `/data`. The official image is pinned to the same Caddy version used by the former custom image. Reusing that mount preserves the CA and its private keys; do not create a replacement TLS directory. Place the supplied `docker/Caddyfile` in the installation directory, preserving any deliberate local customizations. The new override mounts it read-only. `MINIFILES_HTTPS_IMAGE` and `MINIFILES_HTTPS_BUILD_IMAGE` are no longer used and can be removed from the private environment.

Rehearse the transition using copied settings and TLS state in an isolated stack. Check CA-verified HTTPS, login, existing sections and files, then backup. The local smoke script can exercise the transition with `--https --previous-proxy-image OLD_LOCAL_IMAGE` when that old image is available.

If switching to an already-existing reverse proxy instead, follow [INSTALL.md](INSTALL.md#use-an-existing-reverse-proxy). A different proxy may use a different CA; preserve the old TLS backup and plan client trust explicitly.

## Rollback

After a schema migration, switching back to an older image alone may be unsafe. Stop all writers, restore the matching pre-update database and files using the backup guide, restore the corresponding configuration, and select the previous pinned image tag or digest. Rehearse recovery in an isolated project first. Keep the same application key and CA. MiniFiles refuses a database schema newer than the running image understands.
