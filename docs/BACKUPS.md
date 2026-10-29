# Backup and restore

Back up the following separately from the running containers:

- The files in `MINIFILES_DATA_PATH`: MiniFiles does not copy them into SQLite.
- A consistent snapshot of `/config/minifiles.sqlite3`, containing sections and statistics.
- The private `.env` file and persistent `MINIFILES_TLS_PATH`. Restoring the same CA avoids changing client trust.
- The source revision, Compose files and image versions needed to reproduce the service.

Sessions and upload reservations exist only in memory and are not restored. Incomplete files in `.minifiles/uploads/` are temporary and are cleaned up on startup. A backup archive containing `.env` or TLS private keys is itself private; restrict access and store it outside your public checkout.

## Manual SQLite snapshot

With the app running, choose a **new** filename for each snapshot:

```sh
docker compose exec -T minifiles python scripts/backup.py /config/backups/settings-2026-10-29-0800.sqlite3
```

The script uses SQLite's backup API and verifies `PRAGMA integrity_check`. It refuses an existing destination. This includes committed WAL data consistently; copying only the live `.sqlite3` file is not a substitute. Copy the resulting snapshot to a separate backup device, for example:

```sh
docker compose cp minifiles:/config/backups/settings-2026-10-29-0800.sqlite3 /mnt/backup/settings-2026-10-29-0800.sqlite3
```

Replace the example date and destination. Back up `.env` and `tls-data` privately as well. For a simple complete settings/TLS copy, stop this stack while copying those directories; keep the current copy until the backup and restore have been verified. Plan media backups independently, excluding `.minifiles/uploads/`. A snapshot left on the same disk is not protection against that disk failing.

## Optional scheduled companion

`compose.backup.yaml` adds a MiniFiles-only backup container. It uses the same published application image as the main service and runs at **08:00 and 20:00 Europe/Rome**, catches up on the most recent missed slot at startup, retries failures after 15 minutes, and reports unhealthy after 14 hours without success. The schedule and time zone are currently fixed in the script.

The destination must be on a disk separate from the service directory. The script checks both filesystem identity and a `.volume-id` marker before writing. On Linux, first confirm that your backup disk is mounted, create a private directory on it owned by the service UID/GID, then write a marker value you choose into `.volume-id`. Set the same value in `.env`:

```dotenv
MINIFILES_SERVICE_PATH=/srv/minifiles
MINIFILES_BACKUP_PATH=/mnt/backup/minifiles
MINIFILES_BACKUP_VOLUME_ID=your-backup-volume-marker
```

Download the companion configuration into the installation directory:

```sh
curl -fL https://raw.githubusercontent.com/metalogico/minifiles/main/compose.backup.yaml -o compose.backup.yaml
```

Use actual absolute paths. `SERVICE_PATH` is this installation directory containing `.env` and Compose files (and source, if retained). `CONFIG_PATH` and `TLS_PATH` remain those of the main stack; the companion mounts the configured settings directory as `/service/config` and TLS state as `/service/tls-data`. The host must provide `/usr/share/zoneinfo/Europe/Rome`, as mounted by the companion Compose file. The companion expects `MINIFILES_TLS_PATH` to exist. If an external proxy manages TLS, supply an empty private directory here and back up that proxy’s certificates separately.

```sh
docker compose -f compose.yaml -f compose.backup.yaml config --quiet
docker compose -f compose.yaml -f compose.backup.yaml pull
docker compose -f compose.yaml -f compose.backup.yaml up -d --wait
```

Use **both** Compose files for subsequent companion operations. When also using optional HTTPS, include `-f compose.https.yaml` on every command as well. To trigger one backup:

```sh
docker compose -f compose.yaml -f compose.backup.yaml exec -T backup python -m scripts.backup_schedule --once
```

Archives contain a consistent `config/minifiles.sqlite3` snapshot and selected service files under `service/`, including `.env`, TLS state and source when present. The HTTPS Compose override and Caddyfile are included when present. The service tree is mounted read-only except for SQLite's directory, which permits WAL/SHM coordination while the source database itself is opened read-only. The companion has no media mount and does not back up uploaded files. It has no network access and never stops other services. Archives use mode `600`; set the destination directory to `700`. There is no automatic retention cleanup: plan space monitoring and retention yourself.

## Restore into a separate directory

1. Stop only the MiniFiles stack. Preserve its current settings, `.env`, TLS state and source revision before attempting recovery.
2. Inspect the backup archive, then extract the needed snapshot and service files into a new private recovery directory. Do not extract over an active installation. Check the snapshot with SQLite `PRAGMA integrity_check`; the expected result is `ok`.
3. Create an empty settings directory and place the snapshot there as `minifiles.sqlite3`. Do not combine it with old `-wal` or `-shm` files. Apply the configured service UID/GID and private directory permissions.
4. Restore `.env` and TLS state separately, keeping all keys private. Point `MINIFILES_CONFIG_PATH` and `MINIFILES_TLS_PATH` at the recovered directories and confirm `MINIFILES_DATA_PATH` still refers to the correct mounted media filesystem.
5. Start the matching source/image version. Verify CA and hostname, sign in, check sections and browse existing files. Compare known file sizes/checksums for media restored by your separate media backup process.

Keep the pre-restore directories until recovery is verified. Restoring application settings does not restore missing media, resume old uploads or recover old browser sessions.
