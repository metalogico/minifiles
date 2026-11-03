# Development

The backend uses Python 3.12, FastAPI and SQLite, with one Uvicorn worker. The frontend uses Vue 3, TypeScript, Vite and Tailwind CSS.

## Checks

From the repository root:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests -q
.venv/bin/ruff check backend tests
.venv/bin/ruff format --check backend tests
```

For the frontend, using Node 24:

```sh
cd frontend
npm ci
npm test
npm run format:check
npm run build
```

The build includes Vue/TypeScript checking. Frontend tests cover application logic in Node. `ruff format` and `npm run format` apply the repository's formatting rules.

## Running the source

`compose.build.yaml` builds `minifiles:dev` from the checkout. Prepare a private `.env` and writable data/settings directories as described in [Installation](INSTALL.md), then run from the repository root:

```sh
docker compose -f compose.yaml -f compose.build.yaml up -d --build --wait
```

Keep both files in subsequent commands. To include the Caddy proxy, add `-f compose.https.yaml` after them and configure [HTTPS](HTTPS.md).

Use separate storage for development. Credentials, runtime data, TLS state and build output stay out of Git.

## Repository notes

Published migrations must not be edited. Add incremental migrations and run `python3 .github/scripts/check-migrations.py` before merging.

The [publication workflow](../.github/workflows/publish.yml) builds and publishes images when a push updates `main`.
