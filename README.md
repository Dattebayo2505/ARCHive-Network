# ARCHive Network — Facebook Export Curation Tool

A local, two-server web tool that turns a weekly Facebook **"Download Your
Information"** export into a filtered, ready-to-upload folder. You load an export
(a `.zip` or an unzipped folder), pick up to ~10 photos per album plus a still
frame for each video in a browser UI, and click **Build** — the tool writes a
trimmed mirror of the export to `workspace/ready/`. **The original export is
read-only and never modified.** Curation is the only job here; uploading and
loading the curated folder into storage/database are downstream phases.

**Tech stack:** Python 3.12 · FastAPI · Uvicorn · Pydantic · Pillow (backend
JSON API) — and SvelteKit (Svelte 5) · Skeleton v3 · Tailwind v4 · Vite ·
`adapter-node` (frontend UI). Packaged with **uv**; zip extraction shells out to
a vendored 7-Zip binary.

## Prerequisites

- **Windows, macOS, or Linux.** The repo ships a vendored **Windows** 7-Zip
  (`vendor/7za.exe`) used to extract exports fast. On macOS/Linux the tool uses a
  system `7z`/`7za`/`7zz` if one is on `PATH`, and otherwise falls back to
  Python's built-in `zipfile` — so **nothing extra is required** to run
  cross-platform (installing 7-Zip is only a speed optimization on big exports).
- **Python 3.12+**
- A Python installer — either **[uv](https://docs.astral.sh/uv/)** (recommended;
  the repo has a committed `uv.lock`) **or** plain **pip + venv**.
- **Node 20+** — for the SvelteKit frontend.

## Setup

Pick one Python path. Either way, no database, external services, or accounts are
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
# pip install -e ".[dev]"   # add pytest / ruff / httpx for running the tests
cd frontend && npm install
```

## Configuration

Nothing is required to run with defaults. Everything is tunable via environment
variables. Backend settings use the `ARCHIVENETWORK_` prefix (see
`src/archivenetwork/config.py`); the frontend reads `VITE_API_BASE`.

| Variable | Default | Purpose |
|---|---|---|
| `ARCHIVENETWORK_WORKSPACE_DIR` | `workspace` | Root for all generated state, imports, and the `ready/` output. |
| `ARCHIVENETWORK_SEVEN_ZIP_EXE` | `vendor/7za.exe` on Windows; auto-discovered elsewhere | Path to a zip-capable 7-Zip binary. On macOS/Linux, leave unset to auto-detect `7z`/`7za`/`7zz` (falls back to Python's `zipfile` if none), or point it at your own. |
| `ARCHIVENETWORK_MAX_PER_ALBUM` | `10` | Per-album selection cap enforced server-side. |
| `ARCHIVENETWORK_THUMB_SIZE` | `512` | Gallery thumbnail size (px, longest edge). |
| `ARCHIVENETWORK_PREVIEW_SIZE` | `1280` | Full-screen preview render size (px). |
| `ARCHIVENETWORK_HOST` | `127.0.0.1` | API bind host. |
| `ARCHIVENETWORK_PORT` | `8000` | API bind port. |
| `ARCHIVENETWORK_CORS_ORIGINS` / `ARCHIVENETWORK_CORS_ORIGIN_REGEX` | localhost:5173/3000 | Origins allowed to call the API. |
| `VITE_API_BASE` | `http://127.0.0.1:8000` | Base URL the frontend uses to reach the API. |
| `UV_LINK_MODE` | — | Set to `copy` on Windows to dodge a Defender file-lock (`os error 32`) during `uv sync`/`uv run`. |

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
   still frame for each video. Non-album photos are auto-kept.
4. Click **Build ready folder**. The filtered copy lands in
   `workspace/ready/<export-name>/` and the OS file manager pops open on it.

### Headless / utility scripts

Standalone scripts under `scripts/`. Prefix with `uv run` when using uv, or run
with plain `python` inside an activated venv:

```bash
# Non-interactive curation: randomly keep <=N photos/album, keep all non-album
# photos, and build the ready folder. Mirrors the UI's selection + build.
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

> **Known-red on `main`:** three serializer tests assert a pre-timestamp payload
> shape and fail until someone owns them — a clean backend run is "3 failed", not
> a regression. See `CLAUDE.md` for details.

## Where things live

- `src/archivenetwork/` — the FastAPI backend package (see `docs/ARCHITECTURE.md`).
- `frontend/` — the SvelteKit UI.
- `docs/` — design and planning: `PRODUCT.md`, `DESIGN.md`, `PLAN.md`,
  `Pipeline.md`, `Pipeline-Process.md`, and `ARCHITECTURE.md`.
- `workspace/` — all generated output (imports, per-workspace state, the built
  `ready/` folder); gitignored.
- `vendor/7za.exe` — the committed zip extractor.
