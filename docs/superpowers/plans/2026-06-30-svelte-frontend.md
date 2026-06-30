# SvelteKit GUI + FastAPI JSON API — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Jinja2 + Alpine.js server-rendered UI with a SvelteKit GUI that drives FastAPI over a JSON API, with no change to the curation business logic.

**Architecture:** FastAPI becomes a pure JSON API (`/api/*`) plus an image endpoint, with CORS for the UI origins. A new `frontend/` SvelteKit app (Svelte 5, Skeleton v3 on Tailwind v4, `adapter-node`) renders the three screens (ingest → gallery → build summary) and calls the API via a configurable absolute base URL. Two servers run in prod: SvelteKit Node (:3000) and FastAPI (:8000).

**Tech Stack:** FastAPI, Starlette `CORSMiddleware`, pydantic; SvelteKit 2, Svelte 5, `@sveltejs/adapter-node`, Tailwind v4 (`@tailwindcss/vite`), Skeleton v3 (`@skeletonlabs/skeleton` + `@skeletonlabs/skeleton-svelte`), Vitest + `@testing-library/svelte`.

**Spec:** `docs/superpowers/specs/2026-06-30-svelte-frontend-design.md`.

## Global Constraints

- Python **3.12+**. Node **20+** (for SvelteKit 2 / Vite 5).
- Run uv with the Windows-safe prefixes: install/run `UV_LINK_MODE=copy uv run streamlinify`; tests `UV_LINK_MODE=copy uv run --no-sync pytest -q`; lint `uv run ruff check .`. Never invoke bare `python`.
- ruff line-length **100** (E501 not enforced).
- The **≤10-per-named-album cap stays enforced server-side** in `selection/state.py` (the `409` response is the contract). Non-album photos remain auto-kept and read-only. The original export is **read-only**.
- All data endpoints are namespaced under **`/api`**; the image endpoint is `/api/thumb/{fbid}`. `GET /` returns a JSON health object.
- Frontend reads its API base from **`VITE_API_BASE`** (Vite env), default `http://127.0.0.1:8000` (a testable refinement of the spec's "configurable base URL"; same intent).
- CORS allowed origins: `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:3000`, `http://127.0.0.1:3000`.
- Frontend lives in `frontend/`; its build artifacts (`node_modules`, `.svelte-kit`, `build`, `.env`) are gitignored.
- TDD, DRY, YAGNI, frequent commits. No new product features (parity + polish only).

---

## Task B1: Inventory serializer

Pure view-model assembly that combines an `ExportInventory` + `SelectionState` into the JSON payload. Kept separate so it is unit-testable without HTTP.

**Files:**
- Create: `src/streamlinify/web/serializers.py`
- Test: `tests/web/test_serializers.py`

**Interfaces:**
- Consumes: `ExportInventory` (`.albums: list[Album]`, `.non_album_photos: list[Photo]`), `Album` (`.fb_album_id`, `.name`, `.photos: list[Photo]`), `Photo` (`.fbid`, `.caption`, `.exists`), `SelectionState` (`.is_selected(album_fbid, photo_fbid)`, `.count(album_fbid)`).
- Produces: `inventory_payload(export_name: str, inventory: ExportInventory, selection: SelectionState, max_per_album: int) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_serializers.py
from streamlinify.inventory.models import Album, ExportInventory, Photo
from streamlinify.selection.policy import DefaultPolicy
from streamlinify.selection.state import SelectionState
from streamlinify.web.serializers import inventory_payload


def _inv() -> ExportInventory:
    return ExportInventory(
        albums=[
            Album(
                fb_album_id="111",
                name="Animo Fest",
                photos=[
                    Photo(fbid="a01", original_uri="posts/media/x/a01.jpg",
                          resolved_path="x", caption="hi", exists=True, album_fbid="111"),
                    Photo(fbid="a02", original_uri="posts/media/x/a02.jpg",
                          resolved_path="x", caption=None, exists=False, album_fbid="111"),
                ],
            )
        ],
        non_album_photos=[
            Photo(fbid="m01", original_uri="posts/media/y/m01.jpg",
                  resolved_path="y", caption="k", exists=True),
        ],
    )


def test_payload_shape(tmp_path):
    sel = SelectionState(tmp_path / "sel.json", DefaultPolicy())
    sel.toggle("111", "a01")
    payload = inventory_payload("export", _inv(), sel, 10)

    assert payload["export_name"] == "export"
    assert payload["max_per_album"] == 10
    album = payload["albums"][0]
    assert album["fb_album_id"] == "111"
    assert album["name"] == "Animo Fest"
    assert album["count_selected"] == 1
    assert album["photos"][0] == {"fbid": "a01", "caption": "hi", "exists": True, "selected": True}
    assert album["photos"][1]["selected"] is False
    # non-album photos have no `selected` key (read-only, auto-kept)
    assert payload["non_album"][0] == {"fbid": "m01", "caption": "k", "exists": True}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/web/test_serializers.py -q`
Expected: FAIL (`ModuleNotFoundError: streamlinify.web.serializers`).

- [ ] **Step 3: Write minimal implementation**

```python
# src/streamlinify/web/serializers.py
from __future__ import annotations

from ..inventory.models import ExportInventory, Photo
from ..selection.state import SelectionState


def _photo(p: Photo, selected: bool | None = None) -> dict:
    d: dict = {"fbid": p.fbid, "caption": p.caption, "exists": p.exists}
    if selected is not None:
        d["selected"] = selected
    return d


def inventory_payload(
    export_name: str,
    inventory: ExportInventory,
    selection: SelectionState,
    max_per_album: int,
) -> dict:
    albums = [
        {
            "fb_album_id": a.fb_album_id,
            "name": a.name,
            "count_selected": selection.count(a.fb_album_id),
            "photos": [
                _photo(p, selected=selection.is_selected(a.fb_album_id, p.fbid))
                for p in a.photos
            ],
        }
        for a in inventory.albums
    ]
    return {
        "export_name": export_name,
        "max_per_album": max_per_album,
        "albums": albums,
        "non_album": [_photo(p) for p in inventory.non_album_photos],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/web/test_serializers.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/streamlinify/web/serializers.py tests/web/test_serializers.py
git commit -m "feat: inventory JSON serializer for the API"
```

---

## Task B2: Migrate the web layer to the JSON API

Rewrite `app.py` (CORS, drop Jinja2/static) and all three routers to return JSON, plus `config.py` CORS origins. All four web test files are rewritten to the JSON contract in one coherent red→green cycle, because the routers, the app factory, and the shared test flow are mutually coupled (a partial migration would leave the suite broken).

**Files:**
- Modify: `src/streamlinify/config.py`
- Modify: `src/streamlinify/app.py`
- Modify: `src/streamlinify/web/routes_ingest.py`
- Modify: `src/streamlinify/web/routes_gallery.py`
- Modify: `src/streamlinify/web/routes_build.py`
- Test: `tests/web/test_app.py`, `tests/web/test_ingest_routes.py`, `tests/web/test_gallery_routes.py`, `tests/web/test_build_route.py`

**Interfaces:**
- Consumes: `inventory_payload(...)` (B1); `validate_export(folder) -> ValidationReport(ok, missing: list[str], root)`; `find_export_root(folder) -> Path`; `build_inventory(folder) -> ExportInventory`; `SelectionState.toggle/.count/.selected_fbids`, `selection.policy.max_per_album`; `ThumbnailService.thumbnail_path(fbid, source) -> Path`; `build_ready_folder(export_root, dest, keep_fbids) -> BuildResult(ready_root, copied, albums_written, orphans)`; `format_summary(result) -> str`.
- Produces the JSON API in the spec §4: `GET /` (health), `GET /api/session`, `POST /api/ingest/folder` (`{folder}`), `POST /api/ingest/upload` (multipart `file`), `GET /api/inventory`, `GET /api/thumb/{fbid}`, `POST /api/toggle` (`{album_fbid, photo_fbid}`), `POST /api/build`.

- [ ] **Step 1: Write the failing tests (all four web test files)**

```python
# tests/web/test_app.py
from fastapi.testclient import TestClient

from streamlinify.app import create_app


def test_health():
    client = TestClient(create_app())
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"name": "streamlinify", "status": "ok"}


def test_cors_allows_ui_origin():
    client = TestClient(create_app())
    resp = client.get("/", headers={"Origin": "http://localhost:5173"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
```

```python
# tests/web/test_ingest_routes.py
from pathlib import Path

from fastapi.testclient import TestClient

from streamlinify.app import create_app


def test_ingest_folder_ok(export_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # workspace/ is created under cwd
    client = TestClient(create_app())
    resp = client.post("/api/ingest/folder", json={"folder": str(export_root)})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "errors": [], "export_name": "export"}
    assert client.get("/api/session").json() == {"loaded": True, "export_name": "export"}


def test_ingest_folder_invalid(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    resp = client.post("/api/ingest/folder", json={"folder": str(tmp_path)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["errors"]  # non-empty list of missing pieces


def test_session_empty_by_default():
    client = TestClient(create_app())
    assert client.get("/api/session").json() == {"loaded": False, "export_name": None}
```

```python
# tests/web/test_gallery_routes.py
from pathlib import Path

from fastapi.testclient import TestClient

from streamlinify.app import create_app


def _loaded_client(export_root: Path, tmp_path, monkeypatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    return client


def test_inventory_lists_albums(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    resp = client.get("/api/inventory")
    assert resp.status_code == 200
    body = resp.json()
    names = [a["name"] for a in body["albums"]]
    assert "Animo Fest" in names
    assert "Café Night" in names
    assert body["max_per_album"] == 10


def test_inventory_404_without_session(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    assert client.get("/api/inventory").status_code == 404


def test_thumbnail_served(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    resp = client.get("/api/thumb/a01")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")


def test_thumbnail_orphan_404(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    assert client.get("/api/thumb/m02").status_code == 404


def test_toggle_then_cap(export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(export_root, tmp_path, monkeypatch)
    ok = client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": "a01"})
    assert ok.status_code == 200
    assert ok.json() == {"selected": True, "count": 1}

    for n in range(2, 11):  # a02..a10 → reach 10
        client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": f"a{n:02d}"})
    capped = client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": "a11"})
    assert capped.status_code == 409
    assert capped.json()["error"] == "cap"
```

```python
# tests/web/test_build_route.py
from pathlib import Path

from fastapi.testclient import TestClient

from streamlinify.app import create_app


def test_build_produces_ready_folder(export_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": "a01"})

    resp = client.post("/api/build")
    assert resp.status_code == 200
    body = resp.json()
    assert "copied" in body
    assert body["albums_written"] >= 1

    ready = tmp_path / "workspace" / "ready" / "export"
    assert (ready / "posts" / "album" / "0.json").exists()
    # non-album m01 auto-kept even though never toggled
    assert (ready / "posts" / "media" / "Mobileuploads_999" / "m01.jpg").exists()
```

- [ ] **Step 2: Run the web tests to verify they fail**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/web -q`
Expected: FAIL (old routes still HTML/form; new `/api/*` paths 404; health/CORS assertions fail).

- [ ] **Step 3: Add CORS origins to config**

```python
# src/streamlinify/config.py  — add this field inside class Settings (after port)
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
```

- [ ] **Step 4: Rewrite the app factory (CORS, no templates/static)**

```python
# src/streamlinify/app.py  — full file
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings


def create_app() -> FastAPI:
    app = FastAPI(title="Streamlinify")
    app.state.session = None
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    from .web.routes_build import router as build_router
    from .web.routes_gallery import router as gallery_router
    from .web.routes_ingest import router as ingest_router

    app.include_router(ingest_router)
    app.include_router(gallery_router)
    app.include_router(build_router)
    return app
```

- [ ] **Step 5: Rewrite the ingest router (JSON)**

```python
# src/streamlinify/web/routes_ingest.py  — full file
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Request, UploadFile
from pydantic import BaseModel

from ..config import settings
from ..ingest.unzip import extract_zip
from ..ingest.validate import find_export_root, validate_export
from ..inventory.parser import build_inventory
from ..selection.policy import DefaultPolicy
from ..selection.state import SelectionState
from ..thumbnails.service import ThumbnailService
from .session import Session

router = APIRouter()


class FolderRequest(BaseModel):
    folder: str


@router.get("/")
def health() -> dict:
    return {"name": "streamlinify", "status": "ok"}


@router.get("/api/session")
def session_status(request: Request) -> dict:
    session = request.app.state.session
    if session is None:
        return {"loaded": False, "export_name": None}
    return {"loaded": True, "export_name": session.export_root.name}


def _start_session(request: Request, export_root: Path) -> dict:
    report = validate_export(export_root)
    if not report.ok:
        return {"ok": False, "errors": list(report.missing)}
    workspace = settings.workspace_dir
    request.app.state.session = Session(
        export_root=export_root,
        inventory=build_inventory(export_root),
        selection=SelectionState(workspace / "selection.json", DefaultPolicy()),
        thumbnails=ThumbnailService(workspace / "thumbs"),
    )
    return {"ok": True, "errors": [], "export_name": export_root.name}


@router.post("/api/ingest/folder")
def ingest_folder(request: Request, body: FolderRequest) -> dict:
    return _start_session(request, find_export_root(Path(body.folder)))


@router.post("/api/ingest/upload")
def ingest_upload(request: Request, file: UploadFile = File(...)) -> dict:
    workspace = settings.workspace_dir
    import_dir = workspace / "import"
    import_dir.mkdir(parents=True, exist_ok=True)
    zip_path = import_dir / (file.filename or "export.zip")
    zip_path.write_bytes(file.file.read())
    extracted = extract_zip(zip_path, import_dir / "unzipped")
    return _start_session(request, find_export_root(extracted))
```

- [ ] **Step 6: Rewrite the gallery router (JSON)**

```python
# src/streamlinify/web/routes_gallery.py  — full file
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from ..selection.policy import CapExceeded
from .serializers import inventory_payload

router = APIRouter()


class ToggleRequest(BaseModel):
    album_fbid: str
    photo_fbid: str


def _session(request: Request):
    session = request.app.state.session
    if session is None:
        raise HTTPException(status_code=404, detail="No export loaded")
    return session


@router.get("/api/inventory")
def inventory(request: Request) -> dict:
    session = _session(request)
    return inventory_payload(
        session.export_root.name,
        session.inventory,
        session.selection,
        session.selection.policy.max_per_album,
    )


@router.get("/api/thumb/{fbid}")
def thumb(request: Request, fbid: str):
    session = _session(request)
    photo = session.inventory.photo_by_fbid(fbid)
    if photo is None or not photo.exists:
        raise HTTPException(status_code=404, detail="No such photo")
    path = session.thumbnails.thumbnail_path(fbid, photo.resolved_path)
    return FileResponse(path, media_type="image/jpeg")


@router.post("/api/toggle")
def toggle(request: Request, body: ToggleRequest):
    session = _session(request)
    try:
        selected = session.selection.toggle(body.album_fbid, body.photo_fbid)
    except CapExceeded:
        return JSONResponse(
            {"error": "cap", "count": session.selection.count(body.album_fbid)},
            status_code=409,
        )
    return {"selected": selected, "count": session.selection.count(body.album_fbid)}
```

- [ ] **Step 7: Rewrite the build router (JSON)**

```python
# src/streamlinify/web/routes_build.py  — full file
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..config import settings
from ..transform.builder import build_ready_folder
from ..transform.report import format_summary

router = APIRouter()


@router.post("/api/build")
def build(request: Request) -> dict:
    session = request.app.state.session
    if session is None:
        raise HTTPException(status_code=404, detail="No export loaded")

    keep = session.selection.selected_fbids()
    keep |= {p.fbid for p in session.inventory.non_album_photos if p.exists}

    dest = settings.workspace_dir / "ready" / session.export_root.name
    result = build_ready_folder(session.export_root, dest, keep)

    return {
        "copied": result.copied,
        "albums_written": result.albums_written,
        "orphans": result.orphans,
        "summary": format_summary(result),
    }
```

- [ ] **Step 8: Run the full suite to verify green**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest -q`
Expected: PASS (web tests on the JSON contract; all module tests unaffected).

- [ ] **Step 9: Commit**

```bash
git add src/streamlinify/app.py src/streamlinify/config.py src/streamlinify/web/routes_ingest.py src/streamlinify/web/routes_gallery.py src/streamlinify/web/routes_build.py tests/web/test_app.py tests/web/test_ingest_routes.py tests/web/test_gallery_routes.py tests/web/test_build_route.py
git commit -m "feat: convert FastAPI web layer to a JSON API with CORS"
```

---

## Task B3: Remove Jinja2 assets, dead deps, and stray files

Now that nothing renders HTML, delete the templates/static and drop `jinja2`. Also remove the stray root `package.json`/`package-lock.json` (untracked, unrelated to the real `frontend/` project).

**Files:**
- Delete: `src/streamlinify/web/templates/` (4 files), `src/streamlinify/web/static/app.css`
- Modify: `pyproject.toml`
- Delete (untracked): `package.json`, `package-lock.json` at repo root

- [ ] **Step 1: Confirm nothing imports Jinja2 or templates**

Run: `git grep -n -e "Jinja2Templates" -e "templates" -e "StaticFiles" -- src/streamlinify`
Expected: no matches (the B2 rewrite removed them).

- [ ] **Step 2: Delete the template + static assets**

```bash
git rm -r src/streamlinify/web/templates src/streamlinify/web/static
```

- [ ] **Step 3: Remove `jinja2` from dependencies**

In `pyproject.toml`, delete the `"jinja2>=3.1",` line from `[project].dependencies` (keep `python-multipart`, which uploads still need).

- [ ] **Step 4: Remove the stray root Node files**

```bash
rm -f package.json package-lock.json
```

- [ ] **Step 5: Run the full suite + lint to verify green**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest -q`
Expected: PASS.
Run: `uv run ruff check .`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: drop Jinja2 templates/static + jinja2 dep + stray root package.json"
```

---

## Task F1: Scaffold the SvelteKit app shell (Tailwind v4 + Skeleton v3 + adapter-node)

Stand up the `frontend/` project so it builds and renders a styled header. This is setup-heavy but one deliverable: "the app shell builds and runs."

**Files:**
- Create: `frontend/package.json`, `frontend/svelte.config.js`, `frontend/vite.config.js`, `frontend/jsconfig.json`, `frontend/.gitignore`, `frontend/.env`, `frontend/.env.example`
- Create: `frontend/src/app.html`, `frontend/src/app.css`, `frontend/src/routes/+layout.svelte`, `frontend/src/routes/+page.svelte`
- Create: `frontend/static/.gitkeep`

**Interfaces:**
- Produces: a SvelteKit project whose `npm run build` succeeds and whose dev server renders the "Streamlinify — Archers Network" header with Skeleton styling.

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "streamlinify-frontend",
  "private": true,
  "version": "0.0.1",
  "type": "module",
  "scripts": {
    "dev": "vite dev",
    "build": "vite build",
    "preview": "vite preview",
    "start": "node build",
    "sync": "svelte-kit sync",
    "test": "vitest run"
  },
  "devDependencies": {
    "@skeletonlabs/skeleton": "^3",
    "@skeletonlabs/skeleton-svelte": "^1",
    "@sveltejs/adapter-node": "^5",
    "@sveltejs/kit": "^2",
    "@sveltejs/vite-plugin-svelte": "^4",
    "@tailwindcss/vite": "^4",
    "@testing-library/jest-dom": "^6",
    "@testing-library/svelte": "^5",
    "jsdom": "^25",
    "svelte": "^5",
    "tailwindcss": "^4",
    "vite": "^5",
    "vitest": "^2"
  }
}
```

- [ ] **Step 2: Create the config files**

```js
// frontend/svelte.config.js
import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: { adapter: adapter() }
};

export default config;
```

```js
// frontend/vite.config.js
import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()] // tailwind MUST come before sveltekit
});
```

```json
// frontend/jsconfig.json
{
	"extends": "./.svelte-kit/tsconfig.json",
	"compilerOptions": {
		"allowJs": true,
		"checkJs": true,
		"esModuleInterop": true,
		"forceConsistentCasingInFileNames": true,
		"resolveJsonModule": true,
		"skipLibCheck": true,
		"sourceMap": true,
		"strict": true,
		"moduleResolution": "bundler"
	}
}
```

```gitignore
# frontend/.gitignore
node_modules
/build
/.svelte-kit
/package
.env
.env.*
!.env.example
vite.config.js.timestamp-*
```

```bash
# frontend/.env
VITE_API_BASE=http://127.0.0.1:8000
```

```bash
# frontend/.env.example
VITE_API_BASE=http://127.0.0.1:8000
```

- [ ] **Step 3: Create the app HTML + global CSS (Skeleton theme)**

```html
<!-- frontend/src/app.html -->
<!doctype html>
<html lang="en" data-theme="cerberus">
	<head>
		<meta charset="utf-8" />
		<meta name="viewport" content="width=device-width, initial-scale=1" />
		%sveltekit.head%
	</head>
	<body data-sveltekit-preload-data="hover">
		<div style="display: contents">%sveltekit.body%</div>
	</body>
</html>
```

```css
/* frontend/src/app.css */
@import 'tailwindcss';

@import '@skeletonlabs/skeleton';
@import '@skeletonlabs/skeleton/optional/presets';
@import '@skeletonlabs/skeleton/themes/cerberus';

@source '../node_modules/@skeletonlabs/skeleton-svelte/dist';
```

- [ ] **Step 4: Create the layout + a placeholder home page**

```svelte
<!-- frontend/src/routes/+layout.svelte -->
<script>
	import '../app.css';

	let { children } = $props();
</script>

<header class="bg-primary-500 text-white p-4">
	<strong class="text-lg">Streamlinify — Archers Network</strong>
</header>

<main class="p-4">
	{@render children()}
</main>
```

```svelte
<!-- frontend/src/routes/+page.svelte -->
<p class="opacity-70">Ingest screen coming up.</p>
```

```bash
# create the static dir placeholder so SvelteKit has a static root
# frontend/static/.gitkeep  (empty file)
```

- [ ] **Step 5: Install dependencies and generate Kit types**

Run:
```bash
cd frontend
npm install
npx svelte-kit sync
```
Expected: install completes; `.svelte-kit/` is generated. (If the Skeleton install incantation differs for the installed major, cross-check https://www.skeleton.dev/docs/svelte/get-started/installation/sveltekit — the import lines in `app.css` and `data-theme` in `app.html` are the load-bearing parts.)

- [ ] **Step 6: Verify the build succeeds**

Run: `cd frontend && npm run build`
Expected: build completes with no errors (produces `frontend/build/`).

- [ ] **Step 7: Manually verify the shell renders**

Run: `cd frontend && npm run dev` then open http://localhost:5173
Expected: a green ("primary") header reading "Streamlinify — Archers Network" and the placeholder text. Stop the dev server (Ctrl+C) when confirmed.

- [ ] **Step 8: Commit**

```bash
git add frontend/.gitignore frontend/.env.example frontend/package.json frontend/package-lock.json frontend/svelte.config.js frontend/vite.config.js frontend/jsconfig.json frontend/src/app.html frontend/src/app.css frontend/src/routes/+layout.svelte frontend/src/routes/+page.svelte frontend/static/.gitkeep
git commit -m "feat: scaffold SvelteKit app shell with Tailwind v4 + Skeleton v3"
```

---

## Task F2: API client + Vitest (TDD)

A pure JS client around the API base URL, with unit tests (no SvelteKit coupling, so it runs under plain Vitest).

**Files:**
- Create: `frontend/vitest.config.js`, `frontend/vitest-setup.js`
- Create: `frontend/src/lib/api.js`
- Test: `frontend/src/lib/api.test.js`

**Interfaces:**
- Produces: `API_BASE`, `thumbUrl(fbid)`, `getSession(fetchFn?)`, `getInventory(fetchFn?)`, `ingestFolder(folder, fetchFn?)`, `ingestUpload(file, fetchFn?)`, `toggle(albumFbid, photoFbid, fetchFn?)`, `build(fetchFn?)`. `toggle` returns `{ok:true, cap:false, selected, count}` on 200 and `{ok:false, cap:true, count}` on 409. `getInventory` returns `null` on 404. Every function accepts an injectable `fetchFn` (defaults to global `fetch`) so `load` can pass SvelteKit's `fetch` and tests can pass a mock.

- [ ] **Step 1: Create the Vitest config (separate from vite.config so SvelteKit's plugin is not loaded in tests)**

```js
// frontend/vitest.config.js
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { svelteTesting } from '@testing-library/svelte/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [svelte(), svelteTesting()],
	test: {
		environment: 'jsdom',
		setupFiles: ['./vitest-setup.js'],
		globals: true
	}
});
```

```js
// frontend/vitest-setup.js
import '@testing-library/jest-dom/vitest';
```

- [ ] **Step 2: Write the failing test**

```js
// frontend/src/lib/api.test.js
import { describe, expect, it, vi } from 'vitest';
import { getInventory, thumbUrl, toggle } from './api.js';

describe('thumbUrl', () => {
	it('builds an absolute thumb URL', () => {
		expect(thumbUrl('a01')).toMatch(/\/api\/thumb\/a01$/);
	});
});

describe('toggle', () => {
	it('maps a 409 to a cap result', async () => {
		const fakeFetch = vi.fn().mockResolvedValue({
			status: 409,
			json: async () => ({ error: 'cap', count: 10 })
		});
		expect(await toggle('111', 'a11', fakeFetch)).toEqual({ ok: false, cap: true, count: 10 });
	});

	it('maps a 200 to a selected result', async () => {
		const fakeFetch = vi.fn().mockResolvedValue({
			status: 200,
			json: async () => ({ selected: true, count: 1 })
		});
		expect(await toggle('111', 'a01', fakeFetch)).toEqual({
			ok: true,
			cap: false,
			selected: true,
			count: 1
		});
	});
});

describe('getInventory', () => {
	it('returns null when no export is loaded (404)', async () => {
		const fakeFetch = vi.fn().mockResolvedValue({ status: 404, json: async () => ({}) });
		expect(await getInventory(fakeFetch)).toBeNull();
	});
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && npm run test`
Expected: FAIL (`Cannot find module './api.js'`).

- [ ] **Step 4: Write the API client**

```js
// frontend/src/lib/api.js
const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000';

const url = (path) => `${API_BASE}${path}`;
const jsonHeaders = { 'content-type': 'application/json' };

export function thumbUrl(fbid) {
	return url(`/api/thumb/${encodeURIComponent(fbid)}`);
}

export async function getSession(fetchFn = fetch) {
	return (await fetchFn(url('/api/session'))).json();
}

export async function getInventory(fetchFn = fetch) {
	const res = await fetchFn(url('/api/inventory'));
	if (res.status === 404) return null;
	return res.json();
}

export async function ingestFolder(folder, fetchFn = fetch) {
	const res = await fetchFn(url('/api/ingest/folder'), {
		method: 'POST',
		headers: jsonHeaders,
		body: JSON.stringify({ folder })
	});
	return res.json();
}

export async function ingestUpload(file, fetchFn = fetch) {
	const fd = new FormData();
	fd.append('file', file);
	const res = await fetchFn(url('/api/ingest/upload'), { method: 'POST', body: fd });
	return res.json();
}

export async function toggle(albumFbid, photoFbid, fetchFn = fetch) {
	const res = await fetchFn(url('/api/toggle'), {
		method: 'POST',
		headers: jsonHeaders,
		body: JSON.stringify({ album_fbid: albumFbid, photo_fbid: photoFbid })
	});
	if (res.status === 409) {
		const data = await res.json();
		return { ok: false, cap: true, count: data.count };
	}
	const data = await res.json();
	return { ok: true, cap: false, selected: data.selected, count: data.count };
}

export async function build(fetchFn = fetch) {
	return (await fetchFn(url('/api/build'), { method: 'POST' })).json();
}

export { API_BASE };
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && npm run test`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/vitest.config.js frontend/vitest-setup.js frontend/src/lib/api.js frontend/src/lib/api.test.js frontend/package.json frontend/package-lock.json
git commit -m "feat: frontend API client with Vitest unit tests"
```

---

## Task F3: Ingest screen

Replace the placeholder home page with the real ingest form (zip upload + folder path), wired to the API and navigating to the gallery on success.

**Files:**
- Modify: `frontend/src/routes/+page.svelte`

**Interfaces:**
- Consumes: `ingestFolder`, `ingestUpload` (F2); `goto` from `$app/navigation`.

- [ ] **Step 1: Implement the ingest screen**

```svelte
<!-- frontend/src/routes/+page.svelte -->
<script>
	import { goto } from '$app/navigation';
	import { ingestFolder, ingestUpload } from '$lib/api.js';

	let folder = $state('');
	let files = $state(null);
	let errors = $state([]);
	let busy = $state(false);

	async function onResult(result) {
		busy = false;
		if (result.ok) await goto('/gallery');
		else errors = result.errors;
	}

	async function submitUpload(e) {
		e.preventDefault();
		if (!files?.[0]) return;
		busy = true;
		errors = [];
		await onResult(await ingestUpload(files[0]));
	}

	async function submitFolder(e) {
		e.preventDefault();
		busy = true;
		errors = [];
		await onResult(await ingestFolder(folder));
	}
</script>

<section class="max-w-xl space-y-4">
	<form class="card p-4 space-y-2" onsubmit={submitUpload}>
		<label class="label">
			<span>Drop export .zip</span>
			<input class="input" type="file" accept=".zip" bind:files required />
		</label>
		<button class="btn preset-filled" type="submit" disabled={busy}>Upload</button>
	</form>

	<form class="card p-4 space-y-2" onsubmit={submitFolder}>
		<label class="label">
			<span>or folder path</span>
			<input class="input" type="text" bind:value={folder} size="60" required />
		</label>
		<button class="btn preset-filled" type="submit" disabled={busy}>Load</button>
	</form>

	{#if errors.length}
		<ul class="text-error-500">
			{#each errors as e}<li>Missing: {e}</li>{/each}
		</ul>
	{/if}
</section>
```

- [ ] **Step 2: Verify the build succeeds**

Run: `cd frontend && npm run build`
Expected: build completes with no errors.

- [ ] **Step 3: Manually verify against the running API**

Start the API (`UV_LINK_MODE=copy uv run streamlinify`) in one terminal and `cd frontend && npm run dev` in another. At http://localhost:5173, paste a valid export folder path → "Load" → navigates to `/gallery` (which 404s the inventory for now and will be built in F4; a console/network 404 here is expected). Paste an invalid path → the "Missing: …" list appears. Stop both servers when confirmed.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/+page.svelte
git commit -m "feat: ingest screen (zip upload + folder path)"
```

---

## Task F4: Gallery (two-pane, live counters, cap toast)

The core screen: load the inventory, render albums + thumbnail grid, toggle selections server-side, and surface the cap `409` as a Skeleton toast. Includes a unit-tested `PhotoTile` component.

**Files:**
- Create: `frontend/src/routes/gallery/+page.js`
- Create: `frontend/src/routes/gallery/+page.svelte`
- Create: `frontend/src/lib/components/AlbumList.svelte`
- Create: `frontend/src/lib/components/PhotoGrid.svelte`
- Create: `frontend/src/lib/components/PhotoTile.svelte`
- Test: `frontend/src/lib/components/PhotoTile.test.js`

**Interfaces:**
- Consumes: `getInventory`, `toggle`, `thumbUrl` (F2); `redirect` from `@sveltejs/kit`; Skeleton `Toast`, `createToaster` from `@skeletonlabs/skeleton-svelte`.
- `PhotoTile` props: `{ photo: {fbid, exists, selected, caption}, src = '', selectable = true, onToggle }`. It renders a `<button data-testid="tile-<fbid>">`, disabled when `!selectable || !photo.exists`, calling `onToggle(photo)` on click. It imports nothing SvelteKit-specific (so it is testable under plain Vitest).

- [ ] **Step 1: Write the failing PhotoTile test**

```js
// frontend/src/lib/components/PhotoTile.test.js
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import PhotoTile from './PhotoTile.svelte';

describe('PhotoTile', () => {
	it('calls onToggle when an existing, selectable tile is clicked', async () => {
		const onToggle = vi.fn();
		render(PhotoTile, {
			props: {
				photo: { fbid: 'a01', exists: true, selected: false, caption: null },
				src: '/x.jpg',
				selectable: true,
				onToggle
			}
		});
		await fireEvent.click(screen.getByTestId('tile-a01'));
		expect(onToggle).toHaveBeenCalledOnce();
	});

	it('disables an orphan tile', () => {
		render(PhotoTile, {
			props: {
				photo: { fbid: 'm02', exists: false, selected: false, caption: null },
				onToggle: vi.fn()
			}
		});
		expect(screen.getByTestId('tile-m02')).toBeDisabled();
	});
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm run test`
Expected: FAIL (`Cannot find module './PhotoTile.svelte'`).

- [ ] **Step 3: Implement PhotoTile**

```svelte
<!-- frontend/src/lib/components/PhotoTile.svelte -->
<script>
	let { photo, src = '', selectable = true, onToggle } = $props();
</script>

<button
	type="button"
	class="tile border-2 p-0.5 text-left"
	class:border-primary-500={photo.selected}
	class:border-transparent={!photo.selected}
	disabled={!selectable || !photo.exists}
	onclick={() => onToggle?.(photo)}
	data-testid={`tile-${photo.fbid}`}
>
	{#if photo.exists}
		<img class="block h-32 w-32 object-cover" loading="lazy" {src} alt={photo.fbid} />
	{:else}
		<div class="grid h-32 w-32 place-items-center text-xs opacity-60">missing file</div>
	{/if}
	<div class="break-all text-[0.7rem]">{photo.fbid}</div>
	{#if photo.caption}<div class="break-all text-[0.7rem] opacity-70">{photo.caption}</div>{/if}
</button>
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm run test`
Expected: PASS (PhotoTile + the api.js tests).

- [ ] **Step 5: Implement PhotoGrid and AlbumList**

```svelte
<!-- frontend/src/lib/components/PhotoGrid.svelte -->
<script>
	import PhotoTile from './PhotoTile.svelte';

	let { album, thumb, onToggle } = $props();
</script>

<section class="grid gap-2" style="grid-template-columns: repeat(auto-fill, 130px);">
	{#each album.photos as photo (photo.fbid)}
		<PhotoTile {photo} src={photo.exists ? thumb(photo.fbid) : ''} {onToggle} />
	{/each}
</section>
```

```svelte
<!-- frontend/src/lib/components/AlbumList.svelte -->
<script>
	let { albums, nonAlbumCount, maxPerAlbum, activeId, onSelect, onBuild, building } = $props();
</script>

<nav class="w-56 shrink-0 space-y-1">
	{#each albums as a}
		<button
			type="button"
			class="block w-full p-1 text-left"
			class:font-bold={a.fb_album_id === activeId}
			class:text-error-500={a.count_selected >= maxPerAlbum}
			onclick={() => onSelect(a.fb_album_id)}
		>
			{a.name} ({a.count_selected}/{maxPerAlbum})
		</button>
	{/each}
	<hr class="hr" />
	<span class="text-sm opacity-70">Non-album ({nonAlbumCount} kept)</span>
	<hr class="hr" />
	<button class="btn preset-filled w-full" type="button" onclick={onBuild} disabled={building}>
		{building ? 'Building…' : 'Build ready folder ▸'}
	</button>
</nav>
```

- [ ] **Step 6: Implement the gallery load + page**

```js
// frontend/src/routes/gallery/+page.js
import { redirect } from '@sveltejs/kit';
import { getInventory } from '$lib/api.js';

export async function load({ fetch }) {
	const inventory = await getInventory(fetch);
	if (!inventory) throw redirect(307, '/');
	return { inventory };
}
```

```svelte
<!-- frontend/src/routes/gallery/+page.svelte -->
<script>
	import { Toast, createToaster } from '@skeletonlabs/skeleton-svelte';
	import { build, thumbUrl, toggle } from '$lib/api.js';
	import AlbumList from '$lib/components/AlbumList.svelte';
	import PhotoGrid from '$lib/components/PhotoGrid.svelte';
	import BuildSummary from '$lib/components/BuildSummary.svelte';

	let { data } = $props();
	let inventory = $state(data.inventory);
	let activeId = $state(inventory.albums[0]?.fb_album_id ?? null);
	let buildResult = $state(null);
	let building = $state(false);
	const toaster = createToaster();

	let activeAlbum = $derived(inventory.albums.find((a) => a.fb_album_id === activeId) ?? null);

	async function onToggle(photo) {
		if (!activeAlbum) return;
		const result = await toggle(activeAlbum.fb_album_id, photo.fbid);
		if (!result.ok && result.cap) {
			toaster.error({
				title: 'Album is full',
				description: `Max ${inventory.max_per_album} reached.`
			});
			return;
		}
		photo.selected = result.selected;
		activeAlbum.count_selected = result.count;
	}

	async function runBuild() {
		building = true;
		buildResult = await build();
		building = false;
	}
</script>

<div class="flex gap-4">
	<AlbumList
		albums={inventory.albums}
		nonAlbumCount={inventory.non_album.length}
		maxPerAlbum={inventory.max_per_album}
		{activeId}
		onSelect={(id) => (activeId = id)}
		onBuild={runBuild}
		{building}
	/>

	{#if activeAlbum}
		<PhotoGrid album={activeAlbum} thumb={thumbUrl} {onToggle} />
	{/if}
</div>

{#if buildResult}
	<BuildSummary result={buildResult} onClose={() => (buildResult = null)} />
{/if}

<Toast.Group {toaster}>
	{#snippet children(toast)}
		<Toast {toast}>
			<Toast.Message>
				<Toast.Title>{toast.title}</Toast.Title>
				<Toast.Description>{toast.description}</Toast.Description>
			</Toast.Message>
			<Toast.CloseTrigger />
		</Toast>
	{/snippet}
</Toast.Group>
```

Note: `BuildSummary` is created in Task F5. To keep this task's build green on its own, create a one-line stub now and flesh it out in F5:

```svelte
<!-- frontend/src/lib/components/BuildSummary.svelte (stub; replaced in F5) -->
<script>
	let { result, onClose } = $props();
</script>

<button class="btn preset-filled" type="button" onclick={onClose}>Close ({result.copied} copied)</button>
```

- [ ] **Step 7: Verify tests + build**

Run: `cd frontend && npm run test`
Expected: PASS.
Run: `cd frontend && npm run build`
Expected: build completes with no errors.

- [ ] **Step 8: Manually verify the gallery against the running API**

With both servers up (API + `npm run dev`), load a valid export on the ingest screen → the gallery shows the album rail with `X/10` counters and the thumbnail grid. Click tiles to toggle (border highlights, counter updates). Fill an album to 10 then click an 11th → the "Album is full" toast appears and the tile does not select. Stop both servers when confirmed.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/routes/gallery frontend/src/lib/components
git commit -m "feat: gallery with live counters, server-side toggle, and cap toast"
```

---

## Task F5: Build summary modal

Replace the `BuildSummary` stub with a real modal showing the build result.

**Files:**
- Modify: `frontend/src/lib/components/BuildSummary.svelte`

**Interfaces:**
- Consumes: `result` = `{copied, albums_written, orphans: string[], summary: string}` (from `POST /api/build`), `onClose` callback.

- [ ] **Step 1: Implement the modal**

```svelte
<!-- frontend/src/lib/components/BuildSummary.svelte -->
<script>
	let { result, onClose } = $props();
</script>

<div class="fixed inset-0 grid place-items-center bg-black/50" role="dialog" aria-modal="true">
	<div class="card bg-surface-100-900 w-full max-w-lg space-y-2 p-6">
		<h2 class="h3">Build complete</h2>
		<p>Media files copied: {result.copied}</p>
		<p>Albums written: {result.albums_written}</p>
		<p>Orphans: {result.orphans.length}</p>
		<pre class="pre max-h-64 overflow-auto">{result.summary}</pre>
		<button class="btn preset-filled" type="button" onclick={onClose}>Back to gallery</button>
	</div>
</div>
```

- [ ] **Step 2: Verify tests + build**

Run: `cd frontend && npm run test`
Expected: PASS.
Run: `cd frontend && npm run build`
Expected: build completes with no errors.

- [ ] **Step 3: Manually verify the full flow**

With both servers up, load → select photos → "Build ready folder ▸" → the modal shows copied/albums/orphans counts + the summary text; "Back to gallery" closes it. Confirm `workspace/ready/<export>/` was written. Stop both servers when confirmed.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/components/BuildSummary.svelte
git commit -m "feat: build summary modal"
```

---

## Task D1: Documentation

Update `CLAUDE.md`, `README.md`, and add a supersede note to the old design spec.

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-06-28-streamlinify-curation-tool-design.md`

- [ ] **Step 1: Update `CLAUDE.md`**

Replace the **Commands** section with:

```markdown
## Commands
- `UV_LINK_MODE=copy uv run streamlinify` — run the JSON API (http://127.0.0.1:8000)
- `UV_LINK_MODE=copy uv run --no-sync pytest -q` — run backend tests (skips reinstall)
- `uv run ruff check .` — lint (line-length 100; E501 not enforced)
- `cd frontend && npm install && npm run dev` — run the SvelteKit UI (http://localhost:5173)
- `cd frontend && npm run build && node build` — production UI server (http://localhost:3000)
- `cd frontend && npm run test` — frontend Vitest unit tests
```

In **Environment gotchas (Windows)**, add a bullet:

```markdown
- Frontend needs Node 20+. From `frontend/`: `npm install` once, then `npm run dev`. The UI reads
  `VITE_API_BASE` (default `http://127.0.0.1:8000`); both servers must run together.
```

Replace the **Architecture** UI line ("UI is Jinja2 + Alpine.js (CDN), no build step…") with:

```markdown
- UI is a separate **SvelteKit** app in `frontend/` (Svelte 5, Skeleton v3 on Tailwind v4,
  `adapter-node`) talking to FastAPI over a JSON API. `web/` routers are now a thin **JSON API**
  under `/api` (+ `/api/thumb/{fbid}` images) with CORS; no server-rendered HTML. The ≤10/album cap
  is still enforced **server-side** (the `409` response). Two servers run together (API :8000, UI :3000/:5173).
```

- [ ] **Step 2: Update `README.md`**

Replace the **Run**, **Test**, and **Workflow** sections with:

```markdown
## Run

Two servers run together.

```bash
# 1) API
UV_LINK_MODE=copy uv run streamlinify        # http://127.0.0.1:8000

# 2) UI (dev)
cd frontend && npm install && npm run dev     # http://localhost:5173
# UI (prod): cd frontend && npm run build && node build   # http://localhost:3000
```

> On Windows, if `uv` hits a temp-file lock during install, prefix commands with
> `UV_LINK_MODE=copy`. The UI needs Node 20+ and reads `VITE_API_BASE` (default the API above).

## Test

```bash
UV_LINK_MODE=copy uv run --no-sync pytest -q
uv run ruff check .
cd frontend && npm run test
```

## Workflow

1. Start both servers; open the UI.
2. Drop the weekly export `.zip` (or paste the unzipped folder path).
3. Pick ≤10 photos per named album; non-album photos are auto-kept.
4. Click **Build ready folder** → output lands in `workspace/ready/<export-name>/`.
   The original export is never modified.
```

- [ ] **Step 3: Add a supersede note to the 2026-06-28 design**

At the top of `docs/superpowers/specs/2026-06-28-streamlinify-curation-tool-design.md` (just under the title block), add:

```markdown
> **Note (2026-06-30):** the **UI-stack decision** here (Jinja2 + Alpine.js, no build step — §4 row
> "UI stack" and §7) is **superseded by** `2026-06-30-svelte-frontend-design.md` (SvelteKit + Skeleton).
> All other parts of this design still hold.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md README.md docs/superpowers/specs/2026-06-28-streamlinify-curation-tool-design.md
git commit -m "docs: update CLAUDE.md + README for the SvelteKit UI; supersede old UI decision"
```

---

## Final verification

- [ ] Backend: `UV_LINK_MODE=copy uv run --no-sync pytest -q` → all pass; `uv run ruff check .` → clean.
- [ ] Frontend: `cd frontend && npm run test` → all pass; `npm run build` → succeeds.
- [ ] End-to-end (both servers up): ingest a valid export → gallery counters + toggle + cap toast → build modal → `workspace/ready/<export>/` written; original export untouched.
- [ ] No `jinja2` import or `web/templates`/`web/static` remain; stray root `package.json`/`package-lock.json` gone.
- [ ] Ready for `/impeccable init` to audit and polish the running UI.

---

## Self-Review

**Spec coverage:** §3 architecture → B2/F1; §4 API contract → B1/B2 (every endpoint has a test); §5 CORS → B2 (`test_cors_allows_ui_origin`); §6 frontend (routes/components/Skeleton/SSR load) → F1–F5; §7 run/build → F1 + D1; §8 backend changes/deps/cleanup → B2/B3; §9 testing → B1/B2 (backend) + F2/F4 (Vitest); §10 docs → D1; §11 success criteria → Final verification; §12 non-goals → respected (no new features). No gaps.

**Placeholder scan:** No "TBD"/"add error handling"/"similar to" placeholders; the one `BuildSummary` stub in F4 is explicitly a temporary, complete one-liner replaced in F5 (so F4 builds green on its own), not a deferred placeholder.

**Type consistency:** `inventory_payload(export_name, inventory, selection, max_per_album)` matches between B1 and B2. `ToggleRequest{album_fbid, photo_fbid}` matches the api.js body. `toggle()` returns `{ok, cap, selected, count}` consistently between F2's contract, its test, and F4's `onToggle`. `BuildResult` fields (`copied`, `albums_written`, `orphans`) match B2's build route and F5's modal. Endpoint paths match between api.js (F2) and the routers (B2).
