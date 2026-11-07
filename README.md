# ARCHive Network — Facebook Export Curation Tool

A local, two-server web tool that turns a weekly Facebook **"Download Your
Information"** export into a filtered, ready-to-upload folder. You load an export
(a `.zip` or an unzipped folder), pick up to ~10 photos per album plus a still
frame for each video in a browser UI, and click **Build** — the tool writes a
trimmed mirror of the export to `workspace/ready/`. **The original export is
read-only and never modified.**

Curation is the tool's job. An optional **Dev Mode** then **publishes** the built
`ready/` folder to a named *environment*: its S3 bucket plus its DynamoDB tables. The
environment is `local` (the floci emulator in Docker) by default, or the official AWS `dev` / `prod`
after you sign in from the app. The publish reads nothing but the built folder. See **Dev Mode** below.

> **Database:** production uses **Amazon DynamoDB** (decided 2026-10-30). The loader was
> ported from PostgreSQL in November 2026.

**Tech stack:** Python 3.12 · FastAPI · Uvicorn · Pydantic · Pillow · boto3
(backend JSON API) — and SvelteKit (Svelte 5) · Skeleton v3 · Tailwind v4 ·
Vite · `adapter-node` (frontend UI). Packaged with **uv**; zip extraction shells out
to a vendored 7-Zip binary. S3 + DynamoDB (via boto3: the floci emulator in Docker locally, or
AWS) are **optional** and only needed for Dev Mode. **No AWS CLI is needed**; the app signs in to
AWS itself.

## Prerequisites

- **Windows, macOS, or Linux.** The repo ships vendored 7-Zip binaries under `vendor/`
  (`7za.exe` for Windows, `7zz_mac` for macOS, and `7zzs_x64` / `7zzs_x32` for Linux)
  used to extract exports quickly across platforms out of the box. Native tools (`ditto` on
  macOS, `unzip` on Linux) and Python's `zipfile` are also supported as automatic fallbacks.
- **Python 3.12+**
- A Python installer — either **[uv](https://docs.astral.sh/uv/)** (recommended;
  the repo has a committed `uv.lock`), plain **pip + venv**, or **conda / mamba**.
- **Node 20+** — for the SvelteKit frontend.

## Setup

Pick one of the three Python paths below. Whichever you pick, no database, external services, or accounts are
required to curate — the tool runs entirely against your local export. AWS setup (for Dev Mode
only) is the optional last step.

**With uv (recommended):**

```bash
# UV_LINK_MODE=copy avoids a Windows/Defender file-lock during install (harmless elsewhere).
UV_LINK_MODE=copy uv sync
cd frontend && npm install
```

**With plain pip + venv (no uv):**

```bash
python -m venv .venv
# Activate it:  Windows -> .venv\Scripts\activate   |   macOS/Linux -> source .venv/bin/activate
pip install -e .            # runtime deps + the `archivenetwork` command
# pip install -e ".[dev]"   # add pytest / ruff / httpx2 for running the tests
cd frontend && npm install
```

**With conda / mamba:** conda supplies the interpreter; the project's own deps
still come from pip inside that env.

```bash
conda create -n archivenetwork python=3.12     # or: mamba create -n archivenetwork python=3.12
conda activate archivenetwork
pip install -e .            # add ".[dev]" for pytest / ruff
cd frontend && npm install
```

**Optional — publish to AWS from Dev Mode:** copy the committed example to the gitignored
personal file, then fill in the sign-in values from the *Archers Network AWS Guide* (Google
Drive; ask a maintainer for access):

```bash
cp environments.local.toml.example environments.local.toml   # Windows: copy ...
```

Skip this and the app still runs: the AWS environments just show as "not configured", and
`local` (floci) works with no setup at all.

## Configuration

Nothing is required to run with defaults. **`.env` is optional**: machine settings only, each
with a default (see `.env.example`). Backend settings use the `ARCHIVENETWORK_` prefix (see
`src/archivenetwork/config.py`); real environment variables win over `.env`. The frontend reads
`VITE_API_BASE`.

| Variable | Default | Purpose |
|---|---|---|
| `ARCHIVENETWORK_WORKSPACE_DIR` | `workspace` | Root for all generated state, imports, the AWS sign-in cache (`aws/sso/`) and the `ready/` output. |
| `ARCHIVENETWORK_SEVEN_ZIP_EXE` | `vendor/<platform-binary>` | Path to a zip-capable 7-Zip binary (defaults to vendored `7za.exe` on Win, `7zz_mac` on macOS, `7zzs_x64`/`7zzs_x32` on Linux). Override to point to a custom binary if desired. |
| `ARCHIVENETWORK_MAX_PER_ALBUM` | `10` | Per-album selection cap enforced server-side. |
| `ARCHIVENETWORK_THUMB_SIZE` | `512` | Gallery thumbnail size (px, longest edge). |
| `ARCHIVENETWORK_PREVIEW_SIZE` | `1280` | Full-screen preview render size (px). |
| `ARCHIVENETWORK_HOST` | `127.0.0.1` | API bind host. |
| `ARCHIVENETWORK_PORT` | `8000` | API bind port. |
| `ARCHIVENETWORK_CORS_ORIGINS` / `ARCHIVENETWORK_CORS_ORIGIN_REGEX` | localhost:5173/3000 | Origins allowed to call the API. |
| `ARCHIVENETWORK_FLOCI_VERSION_CHECK` | `true` | Log at startup whether the local floci emulator is the latest release (one GitHub call; `false` turns it off). |
| `VITE_API_BASE` | `http://127.0.0.1:8000` | Base URL the frontend uses to reach the API. |
| `UV_LINK_MODE` | — | Set to `copy` on Windows to dodge a Defender file-lock (`os error 32`) during `uv sync`/`uv run`. |

**Environments are not `.env` settings.** Where Dev Mode publishes is defined in two TOML files
at the repo root:

- **`environments.toml`** (committed) defines `local` (floci, the default), `dev` and `prod`.
  Their bucket names and table prefixes are committed, but their sign-in identifiers are left
  empty on purpose, because the repo is public.
- **`environments.local.toml`** (gitignored, from `environments.local.toml.example`) is merged
  over it key by key. It fills in the `dev` / `prod` sign-in values and can add a personal
  environment of your own. A mistake in this file never stops the app: it is ignored and the Dev
  panel names the problem. It can also never remove `prod`'s typed confirm.

The old AWS keys (`ARCHIVENETWORK_DYNAMODB_TABLE_PREFIX`, `ARCHIVENETWORK_DYNAMODB_ENDPOINT_URL`,
`ARCHIVENETWORK_S3_*`, `ARCHIVENETWORK_FLOCI_*`, `ARCHIVENETWORK_MEDIA_*`) are no longer read.
If your `.env` still has them, the backend logs a warning at startup and the Dev panel lists
them, so you can delete them.

## Usage

The tool is **two servers that run together**: the FastAPI JSON API (port 8000)
and the SvelteKit UI (port 5173 in dev, 3000 in prod). The UI talks to the API
over HTTP; both must be running.

### Quick start (one command)

Launch both servers together and stop both cleanly on exit:

```powershell
# Windows — picks free ports automatically, stop by typing `exit`.
.\run.ps1        # or, from cmd.exe:  run.bat
```

```bash
# macOS/Linux — stop with Ctrl+C. Uses uv if installed, else the installed
# `archivenetwork` command, else `python -m archivenetwork`.
bash run.sh
```

### Run the servers manually

Start the API (choose the line matching your setup), then the UI in a second
terminal:

```bash
# API → http://127.0.0.1:8000
UV_LINK_MODE=copy uv run archivenetwork   # with uv
archivenetwork                            # with pip install -e . (console script)
python -m archivenetwork                  # with pip, no console script on PATH

# UI (dev, hot reload) → http://localhost:5173
cd frontend && npm run dev

# UI (production build) → http://localhost:3000
cd frontend && npm run build && node build
```

### The curation workflow

1. Start both servers and open the UI.
2. On the landing screen, drop the weekly export `.zip`, browse to an unzipped
   export folder, or reopen a previous workspace. A dropped/selected `.zip` is
   unzipped **locally** by the server — there is no large HTTP upload.
3. In the gallery, pick up to `MAX_PER_ALBUM` photos per named album and choose a
   still frame for each video. **Nothing is auto-kept** — every photo, video and
   album that ships is one you explicitly picked. Videos are pickable under
   **Videos** (uncapped, as are the derived caption-albums). Photos belonging to
   no album appear under a read-only **Non-Album** entry: they cannot be selected
   and are never built, and the build dialog tells you how many that is.
4. Click **Build ready folder**. The filtered copy lands in
   `workspace/ready/<workspace-id>/` (the friendly `facebook-<page>-<date>` name,
   matching `workspace/state/<id>/`) and the OS file manager pops open on it.

### Dev Mode — publish to an environment (optional)

Curation is the tool's job, but Dev Mode runs the **downstream** phase too: it publishes the
built `ready/` folder to an environment's S3 bucket and DynamoDB tables, then checks what landed.

1. In the UI, open the **settings gear** (header) and switch on **Dev Mode**. A
   **Dev Mode** entry appears in the album rail.
2. **Pick an environment** at the top of the panel. A fresh browser always starts on `local`.
   Any AWS environment shows a coloured banner, and `prod` shows it in red.
   - **`local`:** start floci with `docker compose up -d` (Docker required; port 4566). The
     panel can also start, restart or stop the container for you. Click **Create tables** once.
   - **`dev` / `prod`:** click **Sign in**. A browser tab opens on the AWS sign-in page; check
     that it shows the code from the panel, then approve it. One sign-in covers both. No AWS CLI
     is involved, and nothing in `~/.aws` changes.
3. Click **Publish**. It runs three steps, each reported with a pass/fail per check:
   - **Preflight:** you are signed in to the right account, and the bucket and tables are
     reachable. Nothing is written unless every check passes.
   - **Publish:** the photos are uploaded, then the album and media items are written.
   - **Verify:** every item and object from *this* run is really there.

   **Re-running Publish is always safe.** Files already in the bucket are skipped, and items are
   updated in place.

**Publishing to `prod` asks you to type `prod`** (exactly; pasting is blocked), every time. In
AWS, the same people can write to dev and prod, so this typed confirm is the guard against
publishing to the live site by mistake.

The panel also offers **Auto-curate** (≤10 random photos per album plus every video, as real
picks you can untick), a **validation report**, and a paginated **item browser** with image
previews. **Create / Reset / Delete tables** is offered on `local` only, because AWS tables are
created by hand.

The loader reads **only** the ready folder's JSON manifests — never the raw export, never the
tool's in-memory objects — because that is all the real downstream ETL will have. Photos go to
the bucket under `fb-exports/<hashtag>/<album-slug>/<fbid>.jpg`. Album and media items are written
with DynamoDB `UpdateItem` only, so a re-publish never overwrites what the CMS edited, and an item
the CMS deleted stays deleted (it is skipped and reported, and its bytes are not re-uploaded).
Taxonomy, credits, staff and users are CMS-written, with no source in the export.

> **Upgrading from an older `.env` setup:** `local` now uses the table prefix
> `archers-network-local`. Old floci tables named `archers-network-dev-*` are just test data:
> click **Create tables**, publish again, and delete the old tables in the Floci UI if you like.

### What the AWS account must contain

The AWS side is built **by hand** in the console, not by Terraform. The click-by-click steps,
with the real identifiers, live in the *Archers Network AWS Guide* (Google Drive). This is only
the short contract the app relies on:

- **AWS Organizations + IAM Identity Center** in the official account.
  - An **`Admins`** group for 1–2 officers (MFA, AdministratorAccess).
  - A **`Curators`** group for everyone who publishes from this app *and* everyone who works in
    the CMS. Its `Curators` permission set covers both environments and nothing else in the
    account.
- **What the `Curators` permission set allows:**
  - DynamoDB on all 11 tables of each prefix (`archers-network-dev-*`, `archers-network-prod-*`,
    plus `/index/*`): the app needs `GetItem`, `BatchGetItem`, `UpdateItem`, `Scan` and
    `DescribeTable`, and the CMS needs its own writes.
  - S3 on both media buckets: `ListBucket`, plus `GetObject`, `PutObject` and
    `AbortMultipartUpload` on `<bucket>/*`.
- **Buckets** `archers-network-media-dev` and `archers-network-media-prod`: Block Public Access on,
  versioning on, and default encryption. On **dev only**, a lifecycle rule expires noncurrent
  versions after 7 days.
- **Tables:** all 11 per prefix, exactly as `infra/schema/dynamodb-tables.json` defines them
  (keys and GSIs), on-demand, with point-in-time recovery on.
- **A budget alarm** (about USD 5).
- A **personal** account for alpha testing has the same shape with one user; add it to
  `environments.local.toml` as its own environment.

IAM cannot stop a curator writing to prod, because the same group must reach both environments.
That is why `prod` has the typed confirm, enforced in the app and again by the server.

### Headless / utility scripts

Standalone scripts under `scripts/`. Prefix with `uv run` when using uv, or run
with plain `python` inside an activated venv:

```bash
# Non-interactive curation: randomly pick <=N photos per album (the synthetic
# non-album bucket is skipped — it can never be built) and build the ready folder.
# Nothing is auto-kept.
# Videos are skipped — building one needs a browser-captured still.
uv run python scripts/auto_curate.py <export-path> [--per-album 10] [--seed 0]
# or:  python scripts/auto_curate.py <export-path> [--per-album 10] [--seed 0]

# Report the aspect-ratio distribution of images under workspace/ ready & imports.
uv run python scripts/check_aspect_ratios.py     # or:  python scripts/check_aspect_ratios.py
```

## Testing

```bash
# Backend (pytest, against a synthetic fixture — never the real export).
UV_LINK_MODE=copy uv run --no-sync pytest -q   # with uv (--no-sync skips reinstall)
pytest -q                                       # with pip install -e ".[dev]" in an active venv

# Backend lint (line-length 100; E501 not enforced).
uv run ruff check .                             # or, with pip:  ruff check .

# Frontend unit tests (Vitest).
cd frontend && npm run test
```

The DynamoDB / S3 tests run in two tiers. The unit tier uses **moto** in memory and always
runs; sign-in is tested against stub Identity Center clients. The integration tier
(`tests/loader/test_dynamo_floci.py`, `test_storage_s3_floci.py`, `test_publish_floci.py`)
starts its own throwaway floci container at the pinned version, and **skips** cleanly when
Docker is unreachable, so watch the skip count: a skipped test is not a passing one. No tier ever
touches a configured environment's tables; the fixtures use a separate `-test` prefix.

> **Known-red on `main` (1, frontend):** `WorkspaceList.test.js > requires two steps before
> calling onRemove`. On Node 25+ run the frontend tests as
> `NODE_OPTIONS=--no-experimental-webstorage npm run test`, or every test that touches
> `localStorage` fails too.

## Where things live

- `src/archivenetwork/` — the FastAPI backend package (see `docs/ARCHITECTURE.md`).
- `frontend/` — the SvelteKit UI.
- `docs/` — design and planning: `PRODUCT.md`, `DESIGN.md`, `PLAN.md`,
  `Pipeline.md`, `Pipeline-Process.md`, and `ARCHITECTURE.md`.
- `workspace/` — all generated output (imports, per-workspace state, the built
  `ready/` folder); gitignored.
- `vendor/` — the committed cross-platform zip extractors (`7za.exe`, `7zz_mac`, `7zzs_x64`, `7zzs_x32`).
- `environments.toml` / `environments.local.toml.example` — the named environments Dev Mode
  publishes to (see **Configuration**).
- `infra/` — a git submodule, [arch-config-shared](https://github.com/archers-network/arch-config-shared):
  the shared DynamoDB table contract (`infra/schema/dynamodb-tables.json`). Its Terraform is
  retired, since AWS is now set up by hand per the AWS guide. The app runs without the submodule;
  fetch it with `git submodule update --init` (or clone with `--recurse-submodules`) when you
  work on the table schema. Its root README covers how to change it.
