# Public distribution preparation — 29 October 2026

Historical record of the initial source preparation. Current image publication and optional official-Caddy installation are described in [RELEASING.md](RELEASING.md) and [INSTALL.md](INSTALL.md).

This record covers the local preparation of the application repository. No commit, push, GitHub publication, release or server deployment was performed.

## Source and documentation

- Expanded compressed Python, TypeScript, Vue templates and CSS into readable formatting. Added pinned Ruff and Prettier tooling with repeatable checks.
- Separated queue state/labels and the XHR transfer into named functions; clarified cancellation and completion helpers. Expanded file-type handling, SQL and backend lifecycle/upload operations without changing the API, no-overwrite guarantees or desktop layout.
- Kept the existing FastAPI/SQLite/Vue/Tailwind stack, one worker, streaming writes, directory-descriptor checks, exclusive volume lock and atomic hard-link publication.
- Replaced the installation-specific README with an English public guide covering actual features, use, limitations and a source-built Compose installation. Added installation, development and backup/restore documentation, plus an English placeholder-only `.env.example`.
- Reused the original Sites capture of the existing project website. The image is stored locally with provenance in `images/README.md`; no replacement image was generated.
- Applied the user's choice of MIT licensing. The notice uses the confirmed repository owner's public handle; no claims about who authored the code were added.

The supplied Compose topology was already suitable for distribution: a locally built app and Caddy proxy, non-root identities, persistent bind mounts, no public backend port and no dependency on a published MiniFiles image. Runtime defaults were retained. Public instructions use standard Docker/Git commands and do not require the local RTK shell helper.

## Verification

| Check | Result |
| --- | --- |
| Python API, security, directory and backup suite | 83 passed |
| Frontend queue, selection, statistics and rendering suite | 41 passed |
| Ruff lint and format checks | Passed |
| Prettier check | Passed |
| Vue/TypeScript check and Vite production build | Passed |
| Application and HTTPS Docker builds | Passed for Linux ARM64 and Linux amd64 |
| Example-based Compose installation | Started with empty, isolated data/settings/TLS directories |
| HTTPS API | CA and hostname verified; health, login, CSRF and Secure/HttpOnly/Strict cookie checked |
| Streaming upload | 4,718,592 bytes; destination SHA-256 matched source |
| Duplicate and path safeguards | Duplicate preserved, old overwrite field rejected with 422, traversal and macOS metadata rejected, temporary area empty |
| Container recreation | File, section and CA persisted; previous session invalidated |
| Backup and actual recovery | SQLite snapshot integrity checked; section and nine TLS files restored into separate directories; recovered application started and served the expected section/file |
| Browser | Real local app: login, Settings, section/folder creation, navigation, file picker upload, automatic successful-row removal, search and list view; no JavaScript warnings/errors observed |
| Distribution file audit | Git candidate files checked for private passwords, private keys, common token formats and personal deployment paths; no findings |

Docker verification used only the temporary `minifiles-public-review` project, loopback port 18094 and dedicated ignored directories. Browser verification used a separate loopback development server on port 18095, with synthetic data. Temporary containers and their network were removed after verification; the private test evidence and pre-edit source snapshot remain in ignored `artifacts/public-release/`.

## Limits

- The new upload smoke test was about 4.5 MiB. Earlier local/server verification recorded real 20 GiB uploads, but that benchmark was not repeated for this readability change. No new throughput or memory claim is made.
- Browser checks used loopback HTTP development; HTTPS, certificate trust and cookie flags were checked separately against the real Docker proxy. No client trust stores were changed.
- The amd64 images were built locally; this preparation did not run a new test on physical amd64 hardware or the home server.
- The optional scheduled companion is covered by the existing scheduler/archive tests and Compose validation. A new physical backup disk and twice-daily schedule were not provisioned during this preparation.
- The Python tests retain an upstream Starlette/httpx deprecation warning. It does not fail the suite; no dependency migration was folded into the readability work.
- The application remains add-only at the API level with a writable data mount. It does not provide filesystem immutability, resumable uploads or exclusive disk quotas against other programs.

## Git handoff

The source folder did not initially contain a Git repository. A new local `main` repository was initialised with `origin` set to `https://github.com/metalogico/minifiles.git`. There are no commits and no staged files; the distributable source is available for the user's review and first commit.

Ignore rules keep real environments, local media/settings, TLS keys, dependencies, build output, test artifacts and private deployment records out of Git and the Docker context. Existing private operational notes were preserved in place. The nested landing repository was left intact and is excluded from the application repository, avoiding an accidental embedded-repository entry. No existing history, data or backups were deleted.

Public documentation links use repository-relative paths. GitHub access, the remote repository's current contents and future pushes were not tested or modified. Commit and push remain with the user. No remaining product or licensing decision is required for this handoff.
