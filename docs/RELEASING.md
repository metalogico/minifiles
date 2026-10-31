# Building and publishing MiniFiles

## Workflow

Tests run **locally**, before merging. GitHub Actions only builds and publishes Docker images when a push updates `main`, including a merged pull request. A direct push to main also triggers publication. Pushes to develop, pull requests, Git tags and GitHub Releases do not start any workflow. Use branch protection if main should accept only reviewed merges; remove any required checks that referred to the retired CI workflow.

`.github/workflows/publish.yml` builds `linux/amd64` and `linux/arm64` and publishes:

- `ghcr.io/metalogico/minifiles:latest`: the current published main build.
- `ghcr.io/metalogico/minifiles:sha-<full commit>`: the specific source commit, useful for pinned installations and recovery.

MiniFiles publishes only its application image. Optional HTTPS uses the official Caddy image pinned in `compose.https.yaml`. The SHA is the commit that reaches main, which can differ from the develop commit when a merge commit is created. The image revision label records it. A rerun for the same commit can rebuild dependencies and change the digest; pin the digest if exact image bytes must be retained.

There are no test jobs, automatic commits, Git tags, GitHub Releases or release attachments. A manually created `v1.0.0` Git tag can mark a milestone, but it does **not** create a Docker `1.0.0` tag. Build steps still install production dependencies and compile the frontend: those are required to construct the images, not a hosted test suite.

## GitHub setup

Enable Actions and allow the pinned actions in `publish.yml`. The workflow uses `GITHUB_TOKEN` with `contents: read` and `packages: write`; no personal access token, Docker Hub credentials or write access to Git contents is required. Existing packages must grant this repository Actions write access.

After first publication, set the MiniFiles GHCR package to **Public** in its package settings. Public source visibility does not automatically make a container package public. Verify anonymous pulls and both architectures. Wait for the complete workflow to succeed before updating any installation.

## Local checks before merging

Use a development checkout with its own environment and isolated test data. Install the documented development dependencies first. Fetch origin/main and stable Git tags before running the migration guard, so it can protect already-released migrations too.

```sh
python3 .github/scripts/check-migrations.py
.venv/bin/python -m pytest tests -q
.venv/bin/ruff check backend scripts tests
.venv/bin/ruff format --check backend scripts tests
cd frontend
npm ci
npm test
npm run format:check
npm run build
cd ..
```

Build and exercise the image-only installation locally:

```sh
docker build -t minifiles:ci .
python3 .github/scripts/smoke-install.py
python3 .github/scripts/smoke-install.py --https
```

The smoke check creates its own project and temporary configuration, checks the web response and data persistence after recreation, and removes only its temporary stack. Repeat the build with `--platform linux/amd64` or `--platform linux/arm64` and run the corresponding image when checking another architecture. Never point tests at production data.

## Source builds for development

```sh
docker compose -f compose.yaml -f compose.build.yaml build
docker compose -f compose.yaml -f compose.build.yaml up -d --wait
```

For HTTPS source builds, use all three files: `-f compose.yaml -f compose.build.yaml -f compose.https.yaml`. Caddy is still downloaded from its official image.

Use a dedicated development environment and storage. Keep both `-f` options for subsequent commands. This override uses `minifiles:dev` independently of the production image variable.

## Schema policy from the first public image

The first public image freezes the current schema. This replaces the earlier development policy of editing original migrations. Add new incremental changes in `backend/migrations/vNNN_name.py`, appending its function to `MIGRATIONS` in order. The runner uses a transaction and SQLite `user_version`; version 1 keeps the existing sections/cache schema. Never use `executescript` in a migration, as it can commit the transaction.

The local migration guard checks the initial v1 hashes and all migration files from origin/main and stable Git tags (fetch them before checking). Do not update the hashes to bypass a failure. A new migration needs tests for a fresh database and an upgrade from the previous release with representative existing records/files. Check rollback after a failure and ensure existing values are preserved. Schema downgrades are not automatic; document any required restore procedure in release notes.

See [UPGRADING.md](UPGRADING.md) for the first transition and subsequent updates. Image publication and server deployment are separate operations; the workflow never connects to or updates a server.

References: [GitHub container publication](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images), [Docker multi-platform Actions builds](https://docs.docker.com/build/ci/github-actions/multi-platform/).
