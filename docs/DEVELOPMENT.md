# Development

The application uses Python 3.12, FastAPI, standard-library SQLite and one Uvicorn worker. The frontend uses Vue 3, TypeScript, Vite and Tailwind CSS. Do not introduce React, Material Design or Bootstrap. Preserve streaming uploads, no-overwrite publication, path confinement and the desktop three-column layout when changing code.

## Python

From the repository root:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests -q
.venv/bin/ruff check backend scripts tests
.venv/bin/ruff format --check backend scripts tests
```

Use `.venv/bin/ruff format backend scripts tests` to apply formatting. Ruff's version is pinned in `requirements-dev.txt`; its configuration is in `pyproject.toml`.

## Frontend

Node 24 and npm are used by the pinned Docker builder. From `frontend/`:

```sh
npm ci
npm test
npm run build
npm run format:check
```

`build` runs the TypeScript/Vue check before producing `dist/`. `npm run format` applies the pinned Prettier version and the root `.prettierrc.json` settings. The queue tests cover progress and finalisation, duplicates, cancellation, concurrent additions and session reset. Other tests cover folder selection, macOS metadata filtering and statistics refresh. These are application-logic tests running in Node; they do not render Vue components or use the DOM.

## Regression test policy

Keep regression tests focused on application logic, backend/API contracts, database queries and persistence, migrations, validation, authentication, filesystem safety and concurrency. Frontend queue, file-selection and statistics logic may be tested without rendering components.

Do not add or run UI regression tests: component/SSR rendering, HTML/DOM assertions, CSS or layout checks, interface wording, screenshots, animation timelines or automated browser UI flows. Build, typechecking, lint and HTTP/API/persistence smoke checks remain supported. Historical UI verification reports do not require those tests to be restored.

The permanent project rule is [testing.md](../.agents/rules/testing.md).

## Local app

The supported installation is Docker Compose, described in [INSTALL.md](INSTALL.md). Use a separate Compose project name and separate bind directories for experiments. Do not point tests at an existing media collection.

For direct loopback development, `scripts/local.py --init-only` creates `.env.local` with random credentials only if it does not exist, plus the private local data/settings/TLS directories. Keep these files untracked. After building the frontend and ensuring port 8090 is free:

```sh
.venv/bin/python scripts/local.py
```

This direct server is HTTP at `http://127.0.0.1:8090`, which is permitted only on loopback. For Vite HMR, use `.venv/bin/python scripts/local.py --vite`, and in a second terminal under `frontend/` run `npm run dev -- --host 127.0.0.1 --port 5173`. Vite proxies `/api` to the loopback backend. Keep Docker's HTTPS proxy off that port while using the direct server.

The optional `scripts/large_upload.py` benchmark creates a real large source file, streams it to a disposable local stack, compares SHA-256 and samples application RSS. Read its arguments and available disk space before running it; its default 20 GiB test needs roughly 40 GiB plus reserve. It is not part of the default suite and must never target production.

## Repository hygiene

The root ignore files exclude real `.env` files, runtime data, TLS private state, virtual environments, dependencies, build output and private operational records. Keep only `.env.example` as a distributable configuration example. Do not put credentials in screenshots, fixtures, source, Git remotes or logs. Public docs and the README should describe a fresh installation without personal server addresses or host paths.
