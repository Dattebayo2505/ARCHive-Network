# Streamlinify — SvelteKit GUI + FastAPI JSON API — Design

**Date:** 2026-06-30
**Project:** StreamlinifyArchers (Archers Network / DLSU)
**Status:** Approved design — ready for implementation plan
**Supersedes:** the "Jinja2 + Alpine.js" UI decision in
`docs/superpowers/specs/2026-06-28-streamlinify-curation-tool-design.md` (§4, §7). All
non-UI parts of that design (scope, FB-export rules, module layout, output contract) still hold.

---

## 1. Overview

Replace the server-rendered **Jinja2 + Alpine.js** UI with a **SvelteKit** GUI that talks to
FastAPI over a JSON API. FastAPI stops rendering HTML and becomes a **pure JSON API** plus one
image endpoint; SvelteKit owns all rendering, routing, and interaction.

The business logic is unchanged. Only the `web/` layer and `app.py` change on the Python side;
a new `frontend/` directory holds the SvelteKit app with its own toolchain.

This is a **parity + visual polish** rewrite: the same three logical screens
(ingest → gallery → build summary), the same curation rules (≤10 per named album enforced
server-side, all non-album photos auto-kept and read-only), nicer UI. No new product features.

---

## 2. Decisions (this change)

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | UI stack | **SvelteKit + `adapter-node`** (Svelte 5) | User choice; full framework with routing/SSR. |
| 2 | Component/styling | **Skeleton v3** (built on **Tailwind v4**) | User choice; prebuilt AppBar/Card/Toast/buttons, least custom CSS. |
| 3 | Backend role | **Pure JSON API** + image endpoint; no Jinja2/templates/static | Clean separation; FastAPI becomes the data layer only. |
| 4 | Process model | **Two servers** in prod: SvelteKit Node (:3000) + FastAPI (:8000) | User choice; FastAPI is API-only. |
| 5 | UI → API transport | **Absolute base URL + CORS** (no Kit proxy) | Less code; works for SSR `load` (server fetch, CORS-exempt) and client fetch alike. |
| 6 | Scope | **Parity + visual polish**, no new features | User choice; keep behavior identical, improve UX/visuals. |
| 7 | Frontend location | New `frontend/` directory, separate from `src/` | Keeps Python and JS toolchains isolated. |

---

## 3. Architecture

```
StreamlinifyArchers/
├── pyproject.toml              # python deps (jinja2 removed)
├── src/streamlinify/
│   ├── app.py                  # create_app(): CORS + JSON /api routers (no templates/static)
│   ├── ...                     # ingest/ inventory/ thumbnails/ selection/ transform/  (UNCHANGED)
│   └── web/
│       ├── routes_ingest.py    # JSON: session/, ingest/folder, ingest/upload
│       ├── routes_gallery.py   # JSON: inventory, thumb/{fbid}, toggle
│       ├── routes_build.py     # JSON: build
│       └── session.py          # in-memory single-session holder (UNCHANGED)
│       # templates/ and static/ DELETED
└── frontend/                   # SvelteKit app (Svelte 5, Skeleton v3, Tailwind v4)
    ├── package.json
    ├── svelte.config.js        # adapter-node
    ├── vite.config.js          # tailwindcss() before sveltekit()
    ├── .env                    # PUBLIC_API_BASE=http://127.0.0.1:8000
    └── src/
        ├── app.html            # <html data-theme="cerberus">
        ├── app.css             # tailwind + skeleton + theme imports
        ├── lib/
        │   ├── api.js          # fetch wrappers around PUBLIC_API_BASE
        │   └── components/      # AlbumList, PhotoGrid, PhotoTile, IngestForm, BuildSummary
        └── routes/
            ├── +layout.svelte   # Skeleton AppBar header + Toaster
            ├── +page.svelte     # ingest screen (route "/")
            └── gallery/
                ├── +page.js     # universal load → GET /api/inventory (redirect "/" on 404)
                └── +page.svelte # two-pane gallery + build modal
```

The FastAPI session remains a single in-memory holder on `app.state.session` (local, single-user).
Both the SvelteKit SSR `load` (server-side fetch) and the browser hit the same FastAPI process,
so state stays consistent.

---

## 4. JSON API contract (FastAPI)

All data endpoints live under `/api`. `GET /` returns a small JSON health object
(`{"name":"streamlinify","status":"ok"}`) instead of HTML.

| Method & path | Request | Success | Error |
|---|---|---|---|
| `GET /api/session` | — | `{loaded: bool, export_name: string\|null}` | — |
| `POST /api/ingest/folder` | `{"folder": str}` | `{ok: true, errors: [], export_name}` | `{ok: false, errors: [str]}` (HTTP 200) |
| `POST /api/ingest/upload` | multipart `file` | `{ok: true, errors: [], export_name}` | `{ok: false, errors: [str]}` (HTTP 200) |
| `GET /api/inventory` | — | inventory payload (below) | `404 {detail:"No export loaded"}` |
| `GET /api/thumb/{fbid}` | — | `image/jpeg` bytes | `404` (orphan/unknown fbid) |
| `POST /api/toggle` | `{"album_fbid": str, "photo_fbid": str}` | `{selected: bool, count: int}` | `409 {error:"cap", count: int}` |
| `POST /api/build` | — | `{copied, albums_written, orphans: [str], summary: str}` | `404 {detail:"No export loaded"}` |

**Inventory payload (`GET /api/inventory`):**
```json
{
  "export_name": "export",
  "max_per_album": 10,
  "albums": [
    {
      "fb_album_id": "111",
      "name": "Animo Fest",
      "count_selected": 2,
      "photos": [
        {"fbid": "a01", "caption": "…", "exists": true, "selected": true}
      ]
    }
  ],
  "non_album": [
    {"fbid": "m01", "caption": "…", "exists": true}
  ]
}
```

Notes on the payload:
- `selected` and `count_selected` are derived from `session.selection` at request time, so the UI
  hydrates with correct state after a resume.
- Non-album photos have no `selected` field — they are auto-kept and read-only (Decision B of the
  2026-06-28 design, still enforced by `selection/policy.py`).
- `caption` is the already-mojibake-fixed, hoisted caption from the parser (may be `null`).

**Contract shifts from the current routes:**
- `POST /toggle` moves from **form-encoded** to a **JSON body**.
- Ingest returns **`{ok, errors}`** instead of a `303` redirect — SvelteKit owns navigation.
- `/build` returns **JSON** instead of an HTML summary page.
- Endpoints are namespaced under `/api` (and `/api/thumb/{fbid}` for the image).

---

## 5. CORS

`app.py` adds Starlette's `CORSMiddleware` (no new dependency). Allowed origins are configurable
via settings and default to the dev and prod UI origins:
`http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:3000`, `http://127.0.0.1:3000`.
Allow `GET, POST, OPTIONS` and all headers.

- JSON `fetch` calls (toggle/build/ingest, and client-side re-fetch of inventory) are cross-origin
  and rely on these headers; JSON bodies trigger a CORS preflight that the middleware answers.
- `<img src="…/api/thumb/{fbid}">` is a plain cross-origin image GET — it renders without CORS.
- SvelteKit SSR `load` fetches FastAPI **server-to-server** (Node → FastAPI), which is CORS-exempt.

---

## 6. Frontend design

**Stack setup (Skeleton v3 + Tailwind v4 + SvelteKit):**
- Dependencies: `@sveltejs/kit`, `svelte@5`, `@sveltejs/adapter-node`, `vite`,
  `@skeletonlabs/skeleton`, `@skeletonlabs/skeleton-svelte`, `tailwindcss@4`, `@tailwindcss/vite`.
- `vite.config.js`: `tailwindcss()` plugin **before** `sveltekit()`.
- `svelte.config.js`: `@sveltejs/adapter-node`.
- `src/app.css`:
  ```css
  @import 'tailwindcss';
  @import '@skeletonlabs/skeleton';
  @import '@skeletonlabs/skeleton/optional/presets';
  @import '@skeletonlabs/skeleton/themes/cerberus';
  @source '../node_modules/@skeletonlabs/skeleton-svelte/dist';
  ```
- `src/app.html`: `<html data-theme="cerberus">` (theme can be tuned later toward DLSU green by
  `/impeccable`; the spec does not lock a final palette).

**API client — `lib/api.js`:** reads `PUBLIC_API_BASE` (default `http://127.0.0.1:8000`) and
exposes `getSession()`, `getInventory(fetch)`, `ingestFolder(folder)`, `ingestUpload(file)`,
`toggle(albumFbid, photoFbid)`, `build()`, and `thumbUrl(fbid)`. It centralizes base-URL joining
and maps the `409` cap response to a typed result the gallery can surface as a toast.

**Routes & components:**
- `+layout.svelte` — Skeleton AppBar header ("Streamlinify — Archers Network") and a global
  `Toaster` for cap/error messages.
- `/` (`+page.svelte`) — `IngestForm`: a `.zip` file input (→ `ingestUpload`) and a folder-path
  text input (→ `ingestFolder`). On `{ok:true}` navigate to `/gallery`; on `{ok:false}` render the
  `errors` list inline.
- `/gallery` — universal `load` (`+page.js`) calls `getInventory`; on `404` it `redirect`s to `/`.
  `+page.svelte` renders the two-pane layout:
  - `AlbumList` — left rail: named albums with live `count_selected/max_per_album` counters
    (turning "full" red at the cap) and a read-only "Non-album (N kept)" entry.
  - `PhotoGrid` / `PhotoTile` — right pane thumbnail grid for the active album; clicking a tile
    calls `toggle`, updates the count, and on `409` shows the "album is full" toast. Each tile
    shows its `fbid` and `caption`; orphan (`exists:false`) tiles render a "missing file" placeholder
    and are not selectable.
  - A **Build** button → `build()` → `BuildSummary` shown in a **Skeleton modal**
    (copied / albums_written / orphans + the summary text), with a "Back to gallery" close.

**Rendering:** SSR stays on (adapter-node default); the gallery uses a **universal** `load` so the
first paint is server-rendered and subsequent client navigation re-fetches via the same client.

---

## 7. Run & build model

**Dev (two terminals):**
- API: `UV_LINK_MODE=copy uv run streamlinify` → FastAPI on `http://127.0.0.1:8000`.
- UI: `cd frontend && npm install` (first run) then `npm run dev` → Vite HMR on `http://localhost:5173`.

**Prod (two terminals):**
- API: `UV_LINK_MODE=copy uv run streamlinify`.
- UI: `cd frontend && npm run build && node build` → SvelteKit Node server on `http://localhost:3000`
  (`PORT` / `ORIGIN` configurable via adapter-node env vars).

Gitignore: `frontend/node_modules/`, `frontend/.svelte-kit/`, `frontend/build/`, `frontend/.env`
(a committed `frontend/.env.example` documents `PUBLIC_API_BASE`).

---

## 8. Backend changes, dependencies & cleanup

- `app.py`: remove `Jinja2Templates` and the `/static` `StaticFiles` mount; add `CORSMiddleware`;
  include the rewritten `/api` routers; drop `app.state.templates`.
- `web/`: delete `templates/` and `static/`; rewrite the three router modules to return JSON per §4.
  `web/session.py` is unchanged.
- `pyproject.toml`: **remove `jinja2`**; keep `python-multipart` (upload). No new Python deps
  (CORS ships with Starlette).
- `config.py`: add `cors_origins: list[str]` (defaults per §5). `host`/`port` unchanged.
- Remove the **stray root `package.json` and `package-lock.json`** (currently untracked; they
  describe the repo as a generic commonjs package and are unrelated to the real
  `frontend/package.json`).
- `scripts/auto_curate.py` is unaffected (it imports the business modules directly, not `web/`).

---

## 9. Testing (TDD)

**Backend (pytest, `tests/web/`, rewritten to the JSON contract; red → green):** all four existing
web test files change because the routes change — `test_app.py`, `test_ingest_routes.py`,
`test_gallery_routes.py`, `test_build_route.py`.
- `health`: `GET /` returns the JSON health object (`{"name":"streamlinify","status":"ok"}`),
  replacing the old HTML index assertion in `test_app.py`.
- `ingest`: `POST /api/ingest/folder` with a valid fixture → `{ok:true, export_name:"export"}`;
  with an invalid folder → `{ok:false, errors:[…]}` (HTTP 200). `GET /api/session` reflects load state.
- `inventory`: `GET /api/inventory` JSON contains `"Animo Fest"` and `"Café Night"`, the right
  `max_per_album`, and per-photo `selected` flags.
- `thumb`: `GET /api/thumb/a01` → `image/*`; orphan `GET /api/thumb/m02` → `404`.
- `toggle`: JSON body toggles selection (`{selected:true, count:1}`); reaching the cap returns
  `409`.
- `build`: after a toggle, `POST /api/build` → JSON with `copied`, and the ready folder + non-album
  auto-keep are produced on disk (as today).
- `cors`: an `OPTIONS` preflight (or a `GET` with `Origin`) returns the
  `access-control-allow-origin` header for an allowed origin.

The module-level tests (`ingest`, `inventory`, `selection`, `transform`, `thumbnails`,
`test_config`, `test_fixture`) are **unaffected**.

**Frontend (Vitest):**
- `lib/api.js`: base-URL joining, the `409` → cap-result mapping, and `thumbUrl(fbid)`
  construction.
- `PhotoTile.svelte`: clicking toggles selected state and emits the toggle call; an orphan tile is
  rendered non-selectable.

Playwright end-to-end is out of scope (YAGNI for a local single-user tool).

---

## 10. Documentation updates

- `CLAUDE.md`: replace the "Jinja2 + Alpine.js (CDN), no build step" line with the SvelteKit +
  Skeleton + Tailwind, two-server model; update **Commands** (frontend dev/build) and
  **Architecture** (`web/` is now a JSON API; `frontend/` is the GUI); add a brief frontend/Node
  gotchas note. Keep the "≤10/album cap enforced server-side" line — still true.
- `README.md`: update **Run** (two servers), **Test**, and **Workflow** sections.
- This spec is the design of record; add a one-line "superseded by 2026-06-30 spec" note to the
  UI-stack rows of the 2026-06-28 design.

---

## 11. Success criteria

- `uv run streamlinify` serves the JSON API; `npm run dev` (or `node build`) serves the SvelteKit UI
  that drives it end to end: ingest → browse gallery → pick ≤10/album → build.
- The ≤10 cap is still rejected **server-side** (the `409`), surfaced in the UI as a toast.
- Non-album photos remain auto-kept and read-only.
- Selection survives a restart (unchanged persistence) and the gallery hydrates with correct
  selected state.
- `Build` produces `workspace/ready/<export>/` exactly as before; the original export is untouched.
- All backend web tests pass against the JSON contract; module tests remain green; frontend Vitest
  unit tests pass.
- No `jinja2` import remains; templates/static are gone; `/impeccable init` can audit the running UI.

---

## 12. Non-goals

- No change to ingest/inventory/thumbnails/selection/transform business logic or the FB-export rules.
- No new product features (no search/filter, select-all, keyboard nav, dark-mode toggle).
- No S3/DB/EXIF/video work (still downstream).
- No multi-user, auth, or deployment hardening — local single-user tool.
- No committed build artifacts; no Playwright e2e.
