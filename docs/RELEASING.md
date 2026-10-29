# Building and publishing MiniFiles

## Branches and releases

- `develop`: changes, reviewed source builds and CI. No image publication.
- `main`: reviewed release commits. No automatic deployment or image publication on push.
- A stable Git tag such as `v1.0.0`, on a commit contained in `main`, plus a **published GitHub Release** triggers `release.yml`. A tag push by itself does not publish images. Drafts and prereleases do not publish.

Before tagging, merge the verified changes from develop into main. Update the planned image version in Compose, `.env.example` and installation examples for the new release. The release packager also substitutes the tag's version into image references in the downloadable bundle.

Create the tag and publish its GitHub Release only after CI is green. The release workflow re-runs the checks for that tag, builds and tests containers on native AMD64/ARM64 runners, then builds the multi-platform image with Buildx and publishes it to `ghcr.io/metalogico/minifiles:1.0.0` (using the actual release version). It also publishes `ghcr.io/metalogico/minifiles-https` at the same version.

The final job attaches `minifiles-VERSION-install.tar.gz` and `SHA256SUMS` to the release. These contain Compose, `.env.example`, public docs and any required Caddy config; no private environment, runtime data, dependencies or source checkout is included. Wait for **all jobs** to succeed before announcing availability.

Only exact versions are published; no moving `latest`, major, minor or develop tags are maintained. Never move a release tag or overwrite an announced image version. If a released build needs correction, issue a new patch version. For a partially failed initial run, rerun only failed jobs where possible; rebuilding a package can change its digest even from the same source. An exact digest can also be used in the image environment variable when stronger pinning is needed.

## GitHub setup, once per repository

1. Enable GitHub Actions and allow the pinned actions used in these workflows. CI needs read access to contents; only the publish job gets `packages: write`, and only the installation upload job gets `contents: write`.
2. Authentication uses the repository's `GITHUB_TOKEN`; no personal access token or Docker Hub secret is required. If a package with the same name already exists, grant this repository Actions write access to that package.
3. After the first successful publication, open each GHCR package's settings and set its visibility to **Public**. A public source repository does not by itself guarantee public package visibility. MiniFiles has two packages; both must be public.
4. Verify an anonymous pull using an empty Docker credential config, and inspect the manifest for both `linux/amd64` and `linux/arm64`. Then test the release installation bundle on a disposable host/stack. GHCR permission checks and the first hosted run cannot be validated by a local preparation alone.

Actions are pinned to verified commit SHAs. Review updates explicitly. Optional branch protection can require `CI / tests` and both container jobs before merging into main. Do not let automated dependency or image updates bypass the migration checks.

## CI and local verification

`ci.yml` runs on pushes to main/develop, pull requests and manual dispatch. It runs the application tests and frontend build, checks frozen migrations, builds the actual Dockerfiles on native AMD64 and ARM64, and starts the image-only Compose in an isolated project. The smoke check verifies HTTP (CA-verified HTTPS for MiniFiles), persisted database/file content after recreation, and the unchanged MiniFiles CA. It removes only its own disposable containers and volumes.

For a local smoke check, build `minifiles:ci` from the Dockerfile and `minifiles-https:ci` from `Dockerfile.https`, then run:

```sh
python3 .github/scripts/check-migrations.py
python3 .github/scripts/smoke-install.py
```

The scripts require Python 3, Docker Compose and curl. Release packaging is available locally with `RELEASE_VERSION=1.0.0 python3 .github/scripts/package-release.py`; output goes to ignored `dist-release/`. Packaging includes the release/upgrade guides explicitly and other public documentation from Git's tracked-file list. Include new public documentation in the release commit.

## Source builds

From a source checkout with a dedicated development `.env` and separate storage:

```sh
docker compose -f compose.yaml -f compose.build.yaml build
docker compose -f compose.yaml -f compose.build.yaml up -d --wait
```

Keep both `-f` options for subsequent commands. This override uses `minifiles:dev` and `minifiles-https:dev`, independently of the production image variable. The app use the same build. For an optional backup companion, provide a final override setting its image to the same development image; production backup companions use the published app image automatically. Do not mix image versions across services sharing a database.

## Schema policy from v1.0.0

The first public release freezes the current schema. This replaces the earlier development policy of editing original migrations. Add new incremental changes in `backend/migrations/vNNN_name.py`, appending its function to `MIGRATIONS` in order. The runner uses a transaction and SQLite `user_version`; version 1 keeps the existing sections/cache schema. Never use `executescript` in a migration, as it can commit the transaction.

The CI guard checks the initial v1 hashes and all migration files from stable Git tags. Do not update the hashes to bypass a failure. A new migration needs tests for a fresh database and an upgrade from the previous release with representative existing records/files. Check rollback after a failure and ensure existing values are preserved. Schema downgrades are not automatic; document any required restore procedure in release notes.

See [UPGRADING.md](UPGRADING.md) for the first transition and subsequent updates. Image publication and server deployment are separate operations; these workflows never connect to or update a server.

## Optional operational companions

The normal installation bundle is self-contained. Backup overrides are opt-in and retain their documented external-disk, identity-marker and permission requirements.

References: [GitHub container publication](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images), [Docker multi-platform Actions builds](https://docs.docker.com/build/ci/github-actions/multi-platform/).
