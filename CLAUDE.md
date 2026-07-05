# CLAUDE.md

Local **FastAPI (uv)** tool that curates a weekly Facebook "Download Your Information"
export into a filtered, ready-to-upload folder. Curation only — S3 upload + Postgres load
are downstream phases (see the sibling `this_profile's_activity_across_facebook/` repo's
`PLAN.md` + `docs/ArchersNetworkEERD.md`). Design + plan live in `docs/superpowers/`.

## Commands
- `UV_LINK_MODE=copy uv run streamlinify` — run the JSON API (http://127.0.0.1:8000)
- `UV_LINK_MODE=copy uv run --no-sync pytest -q` — run backend tests (skips reinstall)
- `uv run ruff check .` — lint (line-length 100; E501 not enforced)
- `cd frontend && npm install && npm run dev` — run the SvelteKit UI (http://localhost:5173)
- `cd frontend && npm run build && node build` — production UI server (http://localhost:3000)
- `cd frontend && npm run test` — frontend Vitest unit tests

## Environment gotchas (Windows)
- Bare `python` is a broken uv shim — always use `uv run`.
- uv installs intermittently fail with `os error 32` (Defender locks the console-script
  trampoline). Prefix every uv command with `UV_LINK_MODE=copy`; use `--no-sync` for tests
  (src is on pythonpath, so no install needed); retry `uv sync` a few times for real installs.
- Project is an **editable** install from `src/streamlinify/` — never goes stale once installed.
- Zip extraction shells out to a **vendored 7-Zip** at `vendor/7za.exe` (committed; far faster than
  Python's `zipfile` on the ~875 MB export). Must be the zip-capable build — the reduced `7zr.exe`
  only reads 7z/xz/lzma, **not zip**. Override the path via `STREAMLINIFY_SEVEN_ZIP_EXE`.
- Frontend needs Node 20+. From `frontend/`: `npm install` once, then `npm run dev`. The UI reads
  `VITE_API_BASE` (default `http://127.0.0.1:8000`); both servers must run together.

## Architecture (modularize per functionality)
- `src/streamlinify/` package, src layout. One module = one job: `ingest/` (unzip+validate),
  `inventory/` (models, text, parser), `thumbnails/`, `selection/` (policy + state),
  `transform/` (builder + report), `web/` (thin JSON routers + serializers).
- Business logic lives in the modules; `web/` routers stay thin. `app.py` = `create_app()` factory only.
- UI is a separate **SvelteKit** app in `frontend/` (Svelte 5, Skeleton v3 on Tailwind v4,
  `adapter-node`) talking to FastAPI over a JSON API. `web/` routers are now a thin **JSON API**
  under `/api` (+ `/api/thumb/{fbid}` images) with CORS; no server-rendered HTML. The ≤10/album cap
  is still enforced **server-side** (the `409` response). Two servers run together (API :8000, UI :3000/:5173).
- `GET /api/browse?path=` lists sub-dirs (logic in `ingest/browse.py`) so the ingest screen offers a
  **server-side folder picker** instead of a typed path (browsers can't hand the server an absolute path).

## Design system (frontend)
- `PRODUCT.md` (strategic: register, users, brand) + `DESIGN.md` (visual: the **DLSU-green "archers"**
  theme — calm, light, paper-calm; green for identity/primary action only) are the source of truth
  for UI work. The custom Skeleton theme lives in `frontend/src/app.css`.
- The UI is **deliberately light-only**, locked with `color-scheme: only light` + a class-based
  `dark` variant in `app.css` (Skeleton/Tailwind v4 default to `prefers-color-scheme`, which would
  auto-invert to dark). Don't reintroduce dark mode without a product decision.

## Gallery UI patterns
- The gallery page (`routes/gallery/+page.svelte`) uses a **3-column flex layout**: fixed-width left
  rail (albums), `flex-1` center (photo grid), and a collapsible right rail (`SelectionPanel`).
  The outer container is `flex` (not `grid`) so the third column can appear/disappear without
  re-declaring grid tracks.
- **SelectionPanel** (`lib/components/SelectionPanel.svelte`) shows selected photos for the
  **current active album only** (not all albums). It is collapsible (toggle button in the toolbar)
  and resizable via a drag handle on its left edge (pointer-based resize, 200–600px range).
- Photo thumbnails in both PhotoGrid and SelectionPanel use **CSS `columns` masonry layout** with
  natural aspect ratios: each `<img>` measures `naturalWidth`/`naturalHeight` on load and sets
  `aspect-ratio` on its container. Tiles start as `1/1` squares and snap to the real ratio once
  loaded. SelectionPanel derives its column width from `panelWidth` so thumbnails dynamically
  resize when the panel is dragged.

## FB-export data rules (the parser depends on these)
- Resolve media `uri` by taking the substring from `posts/` onward (strip the export-folder prefix).
- Decode mojibake on all human text: `s.encode("latin-1").decode("utf-8")`, fall back to raw.
- Photo fbid = filename stem; album fbid = trailing id (after last `_`) of the media subdir.
- **Never glob `posts/media/`** (~875 MB) — drive off the JSON, then verify the specific file exists.
- Named `album/*.json` get the ≤10 cap; everything else is "non-album" (kept, currently read-only —
  `selection/policy.py` isolates this rule so it can change later).

## Testing
- TDD. `pytest`, one test file per module, against the **synthetic fixture** (`tests/conftest.py`
  `export_root`) — never the real export. Web routes tested via FastAPI `TestClient`.

## Output contract
- Build writes a filtered mirror to `workspace/ready/<export-name>/` (gitignored). The original
  export is **read-only**, never modified.
