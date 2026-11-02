# MiniFiles

A small, self-hosted file browser for a home server. Browse a mounted drive, organise folder shortcuts, and upload files from a desktop browser. MiniFiles runs in Docker and writes uploads directly to the disk you mount.

[Project website](https://minifiles.metalogico.dev) · [Installation](docs/INSTALL.md) · [Development](docs/DEVELOPMENT.md)

![MiniFiles website showing its animated file browser demo](docs/images/minifiles.png)

## Features

- Browse folders with breadcrumbs, grid and list views, and search within the current folder.
- Add, edit and remove coloured folder shortcuts in Settings. Optionally create missing folders when adding a section.
- Upload individual files or whole folder trees through the picker or drag and drop. Paste files from the clipboard.
- Keep each upload's destination while navigating or opening Settings.
- Transfer one file at a time per page, with progress, finalisation status, errors and queue totals.
- Skip existing files automatically. MiniFiles never overwrites files; existing folders are reused.
- Cancel individual items, or finish the current file and discard the remaining queue.
- View filesystem disk usage and section sizes, refreshed at startup, at the end of a queue, or manually.
- Sign in with one configured account.
- Stream large uploads directly to disk with limited server memory use.

The interface is in English and designed for desktop screens at least 1100 px wide. Names you give files and sections are preserved. Download, preview, rename, move and delete operations are outside this version's scope. Interrupted uploads restart from the beginning.

## Install with Docker Compose

The public image is **`ghcr.io/metalogico/minifiles:latest`**, available for AMD64 and ARM64. Docker Compose 2.24.4 or newer is required.

Follow [Installation](docs/INSTALL.md) to download the configuration, set your credentials and start MiniFiles. For access from another computer, see [HTTPS and network access](docs/HTTPS.md).

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
| `MINIFILES_TLS_PATH` | `/data` in the HTTPS proxy | Optional Caddy CA, certificates and private keys |
| `.env` | Environment variables | Account credentials and deployment settings |

These bind mounts survive container recreation. Sessions are held in memory, so restarting requires signing in again. Data protection and recovery are managed outside MiniFiles.

Let uploads finish before updating, and keep the same `.env`, Compose project, storage paths and override files. Follow [Updating](docs/UPGRADING.md) for the commands and recovery notes.

Run one MiniFiles instance per data directory. Uploaded files use mode `600` and the configured UID/GID; other services need compatible permissions to read them.

## Development

See [Development](docs/DEVELOPMENT.md) for source builds and tests.

## License

[MIT](LICENSE).
