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
- `cd frontend && npm run test -- <path>` — run a single frontend test file

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
- A `ConnectionResetError [WinError 10054]` / `_call_connection_lost` traceback during
  video-thumbnail capture is **benign** Proactor asyncio noise — the browser aborts the `206`
  range stream after grabbing frame 1; the request still completes `200`. Not a bug.

## Architecture (modularize per functionality)
- `src/streamlinify/` package, src layout. One module = one job: `ingest/` (unzip+validate),
  `inventory/` (models, text, parser), `thumbnails/`, `selection/` (policy + state),
  `transform/` (builder + report), `web/` (thin JSON routers + serializers).
- Business logic lives in the modules; `web/` routers stay thin. `app.py` = `create_app()` factory only.
- Per-workspace state lives under `workspace/state/<id>/` (`selection.json`, `renames.json`, `archive.json`, thumb caches); the registry of known workspaces is `workspace/workspaces.json` (`web/registry.py`). Custom album names (via `renames.py`) override the default FB names in the live `inventory`. Zip/upload workspaces are named from the **zip filename**, not the extracted folder.
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
- The UI **defaults to light** (photos read best on a neutral light surface) with an **opt-in dark
  mode** toggled from the header (sun/moon button, upper-right). The `dark` variant is **class-based**
  (`@variant dark` in `app.css`) so the theme is driven only by a `.dark` class on `<html>` — never
  auto-inverted by the OS or a browser's Auto Dark Mode. The class is resolved **pre-paint** by an
  inline script in `app.html` (no theme flash) and kept in sync by `$lib/theme.svelte.js`
  (`localStorage` key `archive-theme`; explicit choice wins, else follows `prefers-color-scheme`).
- **Dark mode is a semantic-token inversion, not per-component `dark:` classes.** A single `.dark`
  block in `app.css` re-declares the `--color-surface-*` ramp (low indices → dark backgrounds, high
  indices → light ink) so all ~300 `bg-/text-/border-surface-*` usages flip at once. DLSU green keeps
  its identity (the deep-green header/buttons already pop on dark); only the pale `bg-primary-100`
  wash is darkened. Two exceptions are handled deliberately: (1) "always-dark" scrims over photos/
  modals are pinned to `bg-black/*` so they don't flip to light; (2) the full-screen photo/video
  viewers carry `.surface-fixed` (re-pins the surface ramp to its light values) because they're a
  dark room in *both* themes. When adding UI, prefer surface/primary tokens and it inverts for free;
  only reach for a `dark:` utility when an element is dual-used as both a light-mode dark scrim and a
  content surface.

## Gallery UI patterns
- The gallery page (`routes/gallery/+page.svelte`) uses a **3-column flex layout**: fixed-width left
  rail (albums), `flex-1` center (photo grid), and a collapsible right rail (`SelectionPanel`).
  The outer container is `flex` (not `grid`) so the third column can appear/disappear without
  re-declaring grid tracks.
- **SelectionPanel** (`lib/components/SelectionPanel.svelte`) shows selected photos for the
  **current active album only** (not all albums). It is collapsible (toggle button in the toolbar)
  and resizable via a drag handle on its left edge (pointer-based resize, 200–600px range).
- The two thumbnail surfaces use **different layouts on purpose**. **PhotoGrid** is a uniform
  **CSS Grid** (`repeat(auto-fill, minmax(<size>, 1fr))`, `ViewControls` sets the min); every tile
  is a fixed **3:2** box with `object-cover` — even heights read best for scanning/selection.
  **SelectionPanel** keeps the **CSS `columns` masonry** with natural aspect ratios: each `<img>`
  measures `naturalWidth`/`naturalHeight` on load and sets `aspect-ratio` on its container (tiles
  start `1/1` and snap once loaded), and its column width derives from `panelWidth` so thumbnails
  re-flow as the panel is dragged.
- **Videos** are a distinct gallery category (`inventory.videos`, `activeId === '__videos__'`),
  never imported: a client-captured still (canvas → `POST /api/video/{fbid}/thumbnail`) replaces
  each in the build, and all are auto-kept. **Gotcha:** set `<video>.crossOrigin` *before* `src`
  or the frame canvas taints and `toBlob` returns **null** (Chrome signals taint via a null
  callback, not a throw). Gate capture on `loadeddata` — an unbuffered frame is 0×0 → null too.
- **Context Menus & Overlays**: Right-clicking albums opens `ContextMenu.svelte`, which natively
  supports nested submenus via CSS `group-hover` (with an invisible padding bridge to prevent hover gaps). 
  Inline editing (like Rename) uses `position: fixed` overlays with `field-sizing: content` so the input 
  expands naturally and breaks out of the sidebar constraints without being clipped.

## FB-export data rules (the parser depends on these)
- Resolve media `uri` by taking the substring from `posts/` onward (strip the export-folder prefix).
- Decode mojibake on all human text: `s.encode("latin-1").decode("utf-8")`, fall back to raw.
- Photo fbid = filename stem; album fbid = trailing id (after last `_`) of the media subdir.
- **Never glob `posts/media/`** (~875 MB) — drive off the JSON, then verify the specific file exists.
- Named `album/*.json` get the ≤10 cap; everything else is "non-album" (kept, currently read-only —
  `selection/policy.py` isolates this rule so it can change later).
- **Archived Albums**: Archived albums are stored intact in `inventory.archived_albums` rather than flattened. The builder actively excludes any photos within these albums. On the frontend, they render directly below the Archive section using Svelte 5 `{#snippet}`s and are visually read-only (unselectable, no hover state, but retain full opacity).
- Videos (`videos.json` → `videos_v2`; `posts/media/videos/*.mp4`) ship with **no thumbnails**.
  Detect by extension (`.mp4/.mov/.webm`), split into `inventory.videos`, and replace with a
  still in the build (feed uri rewritten `.mp4`→`.jpg`); the `.mp4` is never copied.

## Testing
- TDD. `pytest`, one test file per module, against the **synthetic fixture** (`tests/conftest.py`
  `export_root`) — never the real export. Web routes tested via FastAPI `TestClient`.
- Frontend tests use the plain `svelte()` plugin (`vitest.config.js`), **not** sveltekit — so
  `$lib` is aliased there and a `ResizeObserver` stub lives in `vitest-setup.js` (needed for
  `bind:clientWidth/Height`). Keep both, or component tests break.
- **Known-red on `main`:** 3 serializer tests (`test_payload_shape`,
  `test_payload_includes_archive_and_uncapped`, `test_payload_includes_videos`) assert the
  pre-timestamp payload shape (before `cebf333` added post/taken timestamps). Not regressions —
  a clean `pytest -q` is 3-failed until someone owns those tests.

## Output contract
- Build writes a filtered mirror to `workspace/ready/<export-name>/` (gitignored). The original
  export is **read-only**, never modified.
- Custom renames (from the workspace's `state/<id>/renames.json`) are substituted directly into the output JSON files inside `posts/album/` during the build phase, completely replacing the original Facebook dump names on disk in the ready folder.
