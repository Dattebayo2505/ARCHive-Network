# ARCHive Network — Facebook Export Curation Tool

A local, two-server web tool that turns a weekly Facebook **"Download Your
Information"** export into a filtered, ready-to-upload folder. You load an export
(a `.zip` or an unzipped folder), pick up to ~10 photos per album plus a still
frame for each video in a browser UI, and click **Build** — the tool writes a
trimmed mirror of the export to `workspace/ready/`. **The original export is
read-only and never modified.**

Curation is the tool's job. Uploading to S3 is still a downstream phase — but an
optional **Dev Mode** lets you rehearse the rest locally: it runs the real
downstream ETL against a DynamoDB table on the local floci emulator, reading nothing but
the built `ready/` folder. It is off unless you name a table. See **Dev Mode** below.

> **Database:** production uses **Amazon DynamoDB** (decided 2026-10-30). The loader was
> ported from PostgreSQL in November 2026; Dev Mode now loads into a DynamoDB table on floci.

**Tech stack:** Python 3.12 · FastAPI · Uvicorn · Pydantic · Pillow · boto3
(backend JSON API) — and SvelteKit (Svelte 5) · Skeleton v3 · Tailwind v4 ·
Vite · `adapter-node` (frontend UI). Packaged with **uv**; zip extraction shells out
to a vendored 7-Zip binary. DynamoDB (via boto3, on the floci emulator in Docker locally) is
**optional** and only needed for Dev Mode.

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
required — the tool runs entirely against your local export.

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

## Configuration

Nothing is required to run with defaults. Everything is tunable via environment
variables. Backend settings use the `ARCHIVENETWORK_` prefix (see
`src/archivenetwork/config.py`); the frontend reads `VITE_API_BASE`.

| Variable | Default | Purpose |
|---|---|---|
| `ARCHIVENETWORK_WORKSPACE_DIR` | `workspace` | Root for all generated state, imports, and the `ready/` output. |
| `ARCHIVENETWORK_SEVEN_ZIP_EXE` | `vendor/<platform-binary>` | Path to a zip-capable 7-Zip binary (defaults to vendored `7za.exe` on Win, `7zz_mac` on macOS, `7zzs_x64`/`7zzs_x32` on Linux). Override to point to a custom binary if desired. |
| `ARCHIVENETWORK_MAX_PER_ALBUM` | `10` | Per-album selection cap enforced server-side. |
| `ARCHIVENETWORK_THUMB_SIZE` | `512` | Gallery thumbnail size (px, longest edge). |
| `ARCHIVENETWORK_PREVIEW_SIZE` | `1280` | Full-screen preview render size (px). |
| `ARCHIVENETWORK_HOST` | `127.0.0.1` | API bind host. |
| `ARCHIVENETWORK_PORT` | `8000` | API bind port. |
| `ARCHIVENETWORK_CORS_ORIGINS` / `ARCHIVENETWORK_CORS_ORIGIN_REGEX` | localhost:5173/3000 | Origins allowed to call the API. |
| `ARCHIVENETWORK_DYNAMODB_TABLE_PREFIX` | — (unset) | **Enables Dev Mode.** The prefix of the 11 per-type DynamoDB tables, e.g. `archers-network-dev` → `archers-network-dev-album`, `-media`, `-credit`, `-featuring`, `-staffer`, `-staff-term`, `-department`, `-category`, `-channel`, `-service`, `-users`. The loader writes only album and media. Every `/api/dev/*` route 404s while unset. It replaces `ARCHIVENETWORK_DYNAMODB_TABLE`: an old `.env` line with only that name is reported as renamed in the Dev panel instead of silently turning Dev Mode off. |
| `ARCHIVENETWORK_DYNAMODB_ENDPOINT_URL` | `http://127.0.0.1:4566` | Where those tables live: the local floci emulator by default (dummy `test`/`test` credentials). Set it **empty** to mean real AWS (default credential chain); the panel then refuses to create, reset or delete tables, since production tables come from Terraform. |
| `ARCHIVENETWORK_MEDIA_ROOT` | `workspace/store` | Dev-mode local object store (stands in for the S3 bucket). Keys are written below it as `fb-exports/<hashtag>/<album-slug>/<fbid>.jpg`. |
| `ARCHIVENETWORK_FLOCI_VERSION_CHECK` | `true` | Log at startup whether the local floci emulator is the latest release (one GitHub call; `false` turns it off). |
| `ARCHIVENETWORK_MEDIA_BASE_URL` | `/store` | Where the object store is served. In production this is a CDN domain instead. |
| `VITE_API_BASE` | `http://127.0.0.1:8000` | Base URL the frontend uses to reach the API. |
| `UV_LINK_MODE` | — | Set to `copy` on Windows to dodge a Defender file-lock (`os error 32`) during `uv sync`/`uv run`. |

Settings are also read from a **gitignored `.env`** at the repo root, so nothing
has to be exported into your shell or committed:

```ini
ARCHIVENETWORK_DYNAMODB_TABLE_PREFIX=archers-network-dev
```

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

### Dev Mode — run the downstream ETL locally (optional)

Curation is the tool's job, but you can rehearse the **downstream** phase locally:
load the built `ready/` folder into real DynamoDB tables and inspect what lands.

1. Start floci with `docker compose up -d` (Docker required; port 4566), and set a table
   prefix in `.env` (see **Configuration** above). Nothing else in the tool changes; without
   `ARCHIVENETWORK_DYNAMODB_TABLE_PREFIX`, Dev Mode stays off and every `/api/dev/*` route
   404s. The tables don't have to exist yet: the panel creates all 11.
2. In the UI, open the **settings gear** (header) and switch on **Dev Mode**. A
   **Dev Mode** entry appears in the album rail.
3. The panel gives you: **Auto-curate** (pick ≤10 photos per album at random plus
   every video — real, editable picks, not auto-kept), **Create / Reset / Delete tables**
   (emulator only), **Run load**, a **validation report**, and a paginated **item browser**
   (album and media items) that renders each image straight from its `storage_path`.

The loader reads **only** the ready folder's four JSON manifests — never the raw
export, never the tool's in-memory objects — because that is all the real
downstream ETL will have. Photos are copied into a local object store
(`workspace/store/`) under the same key an S3 bucket would use
(`fb-exports/<hashtag>/<album-slug>/<fbid>.jpg`), so `LocalStorage` and
`S3Storage` are interchangeable. The loader writes **album and media items** into their own
DynamoDB tables (`<prefix>-album`, `<prefix>-media`) with `UpdateItem` only, so a load
never overwrites what the CMS edited, and
an item the CMS deleted stays deleted (it is skipped and reported, its bytes not re-uploaded). Taxonomy, credits, staff and users are CMS-written, with no source in the
export.

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

The DynamoDB tests run in two tiers. The unit tier uses **moto** in memory and always
runs. The integration tier (`tests/loader/test_dynamo_floci.py`,
`tests/loader/test_storage_s3_floci.py`) starts its own throwaway floci container at the
pinned version, and **skips** cleanly when Docker is unreachable, so watch the skip count:
a skipped test is not a passing one. Neither tier ever touches your configured table; the
fixtures derive a separate `-test` table name.

> **Known-red on `main` (4):** `tests/test_naming.py` (2),
> `test_registry.py::test_register_is_idempotent_on_id_and_sets_last_active`, and
> `test_video_routes.py::test_thumbnail_missing_then_saved`. A clean backend run is
> "4 failed", not a regression. See `CLAUDE.md`.

## Where things live

- `src/archivenetwork/` — the FastAPI backend package (see `docs/ARCHITECTURE.md`).
- `frontend/` — the SvelteKit UI.
- `docs/` — design and planning: `PRODUCT.md`, `DESIGN.md`, `PLAN.md`,
  `Pipeline.md`, `Pipeline-Process.md`, and `ARCHITECTURE.md`.
- `workspace/` — all generated output (imports, per-workspace state, the built
  `ready/` folder); gitignored.
- `vendor/` — the committed cross-platform zip extractors (`7za.exe`, `7zz_mac`, `7zzs_x64`, `7zzs_x32`).
- `infra/` — a git submodule, [arch-config-shared](https://github.com/archers-network/arch-config-shared):
  the AWS Terraform and the shared DynamoDB table contract (`infra/schema/`). The app runs
  without it; fetch it with `git submodule update --init` (or clone with `--recurse-submodules`)
  when you work on infrastructure or the table schema. Its root README covers how to change it.
