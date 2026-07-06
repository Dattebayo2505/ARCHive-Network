# Multi-workspace Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the volunteer keep multiple unzipped Facebook exports side by side, pick which to work on from the landing page, and have each one persist and restore its own kept photos, album renames, and archived albums.

**Architecture:** A `workspace/workspaces.json` registry records every ingested export; each workspace gets its own `workspace/state/<id>/` directory holding `selection.json`, `renames.json`, `archive.json`, and thumbnail caches. Export media is referenced in place, never copied. The session becomes workspace-aware, album-archive state becomes persisted (it is memory-only today), and the SvelteKit landing page gains a workspace picker with auto-resume of the last-active workspace.

**Tech Stack:** Python 3.13 / FastAPI (uv-managed), pytest + FastAPI `TestClient`, SvelteKit (Svelte 5, adapter-node), Vitest.

## Global Constraints

- Run backend tests with `UV_LINK_MODE=copy uv run --no-sync pytest -q` (src is on pythonpath; `--no-sync` skips reinstall). Prefix every uv command with `UV_LINK_MODE=copy`.
- Run a single test: `UV_LINK_MODE=copy uv run --no-sync pytest -q tests/path/test_file.py::test_name`.
- Lint: `uv run ruff check .` (line-length 100; E501 not enforced).
- Frontend tests: `cd frontend && npm run test -- <path>` (Vitest, plain `svelte()` plugin — `$lib` aliased in `vitest.config.js`; `ResizeObserver` stubbed in `vitest-setup.js`).
- All backend tests run against the **synthetic fixtures** in `tests/conftest.py` (`export_root`, etc.) — never the real export.
- `settings.workspace_dir` is the relative `Path("workspace")`; tests `monkeypatch.chdir(tmp_path)` so it resolves under a temp dir.
- Business logic lives in modules; `web/` routers stay thin. One module = one job.
- The original export is **read-only** — never modified. All persisted state lives under `workspace/` (gitignored).
- Windows: bare `python` is broken — always `uv run`. Deleting large trees can hit `PermissionError` / `WinError 32`; deletion code must verify removal actually happened.

## File Structure

**Create:**
- `src/streamlinify/inventory/naming.py` — folder-name → display-name (pure).
- `src/streamlinify/web/registry.py` — `WorkspaceRegistry` + `WorkspaceEntry` over `workspace/workspaces.json`.
- `src/streamlinify/selection/archive_state.py` — `ArchiveState`, persists archived album fbids.
- `src/streamlinify/web/routes_workspaces.py` — `/api/workspaces` list/open/remove.
- `tests/test_naming.py`, `tests/web/test_registry.py`, `tests/test_archive_state.py`, `tests/web/test_routes_workspaces.py`.
- `frontend/src/lib/components/WorkspaceList.svelte` + `frontend/src/lib/components/WorkspaceList.test.js`.

**Modify:**
- `src/streamlinify/web/session.py` — add `workspace_id`, `state_dir`, `archive` to `Session`.
- `src/streamlinify/web/routes_ingest.py` — workspace-aware `_start_session`, per-workspace state dirs, dedup, legacy migration, extended `/api/session`.
- `src/streamlinify/web/routes_gallery.py` — persist archive on archive/unarchive.
- `src/streamlinify/app.py` — init `app.state.registry`, include the workspaces router.
- `frontend/src/lib/api.js` — `listWorkspaces`, `openWorkspace`, `removeWorkspace`.
- `frontend/src/routes/+page.svelte` — workspace list + auto-resume.
- `frontend/src/routes/gallery/+page.svelte` + `frontend/src/routes/gallery/+page.js` — "Switch workspace" + active-workspace name.
- `tests/web/test_ingest_routes.py`, `tests/web/test_gallery_routes.py` — updated expectations.

---

### Task 1: Display-name derivation (`inventory/naming.py`)

**Files:**
- Create: `src/streamlinify/inventory/naming.py`
- Test: `tests/test_naming.py`

**Interfaces:**
- Produces: `display_name(export_name: str) -> str`

- [ ] **Step 1: Write the failing test**

`tests/test_naming.py`:
```python
from streamlinify.inventory.naming import display_name


def test_derives_name_and_drops_random_suffix():
    assert (
        display_name("facebook-ArchersNetwork-2026-07-03-7xOuGnNl")
        == "Archers Network Facebook Export | 2026-07-03"
    )


def test_drops_trailing_annotation_after_suffix():
    assert (
        display_name("facebook-ArchersNetwork-2026-06-08-Th2bzEER_previous-week-posts")
        == "Archers Network Facebook Export | 2026-06-08"
    )


def test_falls_back_to_raw_name_when_no_date():
    assert display_name("export") == "export"
    assert display_name("some-random-folder") == "some-random-folder"


def test_splits_multiword_camelcase_page_name():
    assert (
        display_name("facebook-SomeLongPageName-2026-01-02-abc")
        == "Some Long Page Name Facebook Export | 2026-01-02"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest -q tests/test_naming.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'streamlinify.inventory.naming'`.

- [ ] **Step 3: Write minimal implementation**

`src/streamlinify/inventory/naming.py`:
```python
from __future__ import annotations

import re

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Insert a space between a lowercase/digit and a following uppercase letter.
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def display_name(export_name: str) -> str:
    """Turn an FB export folder name into a friendly label.

    ``facebook-ArchersNetwork-2026-07-03-7xOuGnNl`` ->
    ``Archers Network Facebook Export | 2026-07-03``.

    Rule: strip a leading ``facebook-``; find the first YYYY-MM-DD date; the page
    name is everything before it (CamelCase-split, ``-``/``_`` collapsed to spaces);
    everything after the date (random suffix, ``_annotation``) is dropped. If no
    date is present, return the raw name unchanged.
    """
    name = export_name
    if name.startswith("facebook-"):
        name = name[len("facebook-"):]

    match = _DATE.search(name)
    if match is None:
        return export_name

    page_raw = name[: match.start()].strip("-_ ")
    date = match.group(0)
    page = _CAMEL.sub(" ", page_raw)
    page = re.sub(r"[-_\s]+", " ", page).strip()
    return f"{page} Facebook Export | {date}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest -q tests/test_naming.py`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/streamlinify/inventory/naming.py tests/test_naming.py
git commit -m "feat: derive friendly workspace display name from export folder name"
```

---

### Task 2: Workspace registry (`web/registry.py`)

**Files:**
- Create: `src/streamlinify/web/registry.py`
- Test: `tests/web/test_registry.py`

**Interfaces:**
- Consumes: `display_name` (Task 1).
- Produces:
  - `WorkspaceEntry` dataclass: `id: str`, `export_root: str`, `display_name: str`, `managed: bool`, `created_ts: float`, `last_opened_ts: float`.
  - `WorkspaceRegistry(path: Path)` with:
    - `list() -> list[WorkspaceEntry]` (sorted by `last_opened_ts` desc)
    - `get(ws_id: str) -> WorkspaceEntry | None`
    - `register(export_root: Path, *, managed: bool, now: float) -> WorkspaceEntry` (idempotent on `export_root.name`; sets `last_active`)
    - `remove(ws_id: str) -> WorkspaceEntry | None`
    - `last_active: str | None` (property)

- [ ] **Step 1: Write the failing test**

`tests/web/test_registry.py`:
```python
from pathlib import Path

from streamlinify.web.registry import WorkspaceRegistry


def test_register_is_idempotent_on_id_and_sets_last_active(tmp_path: Path):
    reg = WorkspaceRegistry(tmp_path / "workspaces.json")
    root = tmp_path / "facebook-ArchersNetwork-2026-07-03-abc"
    root.mkdir()

    e1 = reg.register(root, managed=True, now=100.0)
    e2 = reg.register(root, managed=True, now=200.0)

    assert e1.id == "facebook-ArchersNetwork-2026-07-03-abc"
    assert e1.display_name == "Archers Network Facebook Export | 2026-07-03"
    assert len(reg.list()) == 1                # not duplicated
    assert e2.last_opened_ts == 200.0
    assert reg.last_active == e1.id


def test_list_sorted_by_last_opened_desc(tmp_path: Path):
    reg = WorkspaceRegistry(tmp_path / "workspaces.json")
    a = tmp_path / "facebook-A-2026-01-01-x"; a.mkdir()
    b = tmp_path / "facebook-B-2026-02-02-y"; b.mkdir()
    reg.register(a, managed=True, now=100.0)
    reg.register(b, managed=True, now=300.0)

    assert [e.id for e in reg.list()] == [b.name, a.name]


def test_remove_drops_entry_and_clears_last_active(tmp_path: Path):
    reg = WorkspaceRegistry(tmp_path / "workspaces.json")
    a = tmp_path / "facebook-A-2026-01-01-x"; a.mkdir()
    reg.register(a, managed=True, now=100.0)

    removed = reg.remove(a.name)
    assert removed is not None
    assert reg.get(a.name) is None
    assert reg.last_active is None


def test_persists_across_instances(tmp_path: Path):
    path = tmp_path / "workspaces.json"
    a = tmp_path / "facebook-A-2026-01-01-x"; a.mkdir()
    WorkspaceRegistry(path).register(a, managed=False, now=100.0)

    reloaded = WorkspaceRegistry(path)
    entry = reloaded.get(a.name)
    assert entry is not None
    assert entry.managed is False
    assert reloaded.last_active == a.name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest -q tests/web/test_registry.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'streamlinify.web.registry'`.

- [ ] **Step 3: Write minimal implementation**

`src/streamlinify/web/registry.py`:
```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ..inventory.naming import display_name


@dataclass
class WorkspaceEntry:
    id: str
    export_root: str
    display_name: str
    managed: bool
    created_ts: float
    last_opened_ts: float


class WorkspaceRegistry:
    """Persisted list of known workspaces in ``workspace/workspaces.json``.

    Timestamps are supplied by the caller (the route layer passes ``time.time()``)
    so this module has no wall-clock dependency and stays trivially testable.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._entries: dict[str, WorkspaceEntry] = {}
        self._last_active: str | None = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        self._last_active = data.get("last_active")
        for raw in data.get("workspaces", []):
            entry = WorkspaceEntry(**raw)
            self._entries[entry.id] = entry

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "last_active": self._last_active,
            "workspaces": [asdict(e) for e in self._entries.values()],
        }
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def list(self) -> list[WorkspaceEntry]:
        return sorted(self._entries.values(), key=lambda e: e.last_opened_ts, reverse=True)

    def get(self, ws_id: str) -> WorkspaceEntry | None:
        return self._entries.get(ws_id)

    def register(self, export_root: Path, *, managed: bool, now: float) -> WorkspaceEntry:
        ws_id = export_root.name
        entry = self._entries.get(ws_id)
        if entry is None:
            entry = WorkspaceEntry(
                id=ws_id,
                export_root=str(export_root),
                display_name=display_name(ws_id),
                managed=managed,
                created_ts=now,
                last_opened_ts=now,
            )
            self._entries[ws_id] = entry
        else:
            entry.export_root = str(export_root)
            entry.managed = managed
            entry.last_opened_ts = now
        self._last_active = ws_id
        self._save()
        return entry

    def remove(self, ws_id: str) -> WorkspaceEntry | None:
        entry = self._entries.pop(ws_id, None)
        if entry is not None:
            if self._last_active == ws_id:
                self._last_active = None
            self._save()
        return entry

    @property
    def last_active(self) -> str | None:
        return self._last_active
```

- [ ] **Step 4: Run test to verify it passes**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest -q tests/web/test_registry.py`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/streamlinify/web/registry.py tests/web/test_registry.py
git commit -m "feat: workspace registry persisting known exports"
```

---

### Task 3: Archive state persistence (`selection/archive_state.py`)

**Files:**
- Create: `src/streamlinify/selection/archive_state.py`
- Test: `tests/test_archive_state.py`

**Interfaces:**
- Produces: `ArchiveState(path: Path)` with `archived_ids() -> set[str]`, `add(album_fbid: str) -> None`, `remove(album_fbid: str) -> None`, `is_archived(album_fbid: str) -> bool`. Backing file = a JSON array of album fbids.

- [ ] **Step 1: Write the failing test**

`tests/test_archive_state.py`:
```python
from pathlib import Path

from streamlinify.selection.archive_state import ArchiveState


def test_add_remove_roundtrip(tmp_path: Path):
    path = tmp_path / "archive.json"
    state = ArchiveState(path)
    assert state.archived_ids() == set()

    state.add("111")
    state.add("222")
    assert state.is_archived("111")
    assert state.archived_ids() == {"111", "222"}

    state.remove("111")
    assert not state.is_archived("111")
    assert state.archived_ids() == {"222"}


def test_persists_across_instances(tmp_path: Path):
    path = tmp_path / "archive.json"
    ArchiveState(path).add("333")

    assert ArchiveState(path).archived_ids() == {"333"}


def test_add_is_idempotent(tmp_path: Path):
    state = ArchiveState(tmp_path / "archive.json")
    state.add("111")
    state.add("111")
    assert state.archived_ids() == {"111"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest -q tests/test_archive_state.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'streamlinify.selection.archive_state'`.

- [ ] **Step 3: Write minimal implementation**

`src/streamlinify/selection/archive_state.py`:
```python
from __future__ import annotations

import json
from pathlib import Path


class ArchiveState:
    """Persists which albums the user has archived, in ``archive.json``.

    Mirrors ``RenameState``: a small JSON file (an array of album fbids) that
    survives reload/restart so archived albums are restored when the workspace
    is reopened. The in-memory ``inventory.archived_albums`` move is layered on
    top of this at session-build time.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._ids: set[str] = set()
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._ids = set(data)
            except (json.JSONDecodeError, OSError, TypeError):
                pass

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(sorted(self._ids), indent=2), encoding="utf-8")

    def archived_ids(self) -> set[str]:
        return set(self._ids)

    def is_archived(self, album_fbid: str) -> bool:
        return album_fbid in self._ids

    def add(self, album_fbid: str) -> None:
        if album_fbid not in self._ids:
            self._ids.add(album_fbid)
            self._save()

    def remove(self, album_fbid: str) -> None:
        if album_fbid in self._ids:
            self._ids.discard(album_fbid)
            self._save()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest -q tests/test_archive_state.py`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/streamlinify/selection/archive_state.py tests/test_archive_state.py
git commit -m "feat: persist archived-album state per workspace"
```

---

### Task 4: Workspace-aware session + per-workspace state (`session.py`, `routes_ingest.py`, `app.py`)

This task rewires ingest so every workspace stores its own state under `workspace/state/<id>/`, adds the registry to app state, persists/restores archived albums at session-build time, and migrates legacy flat state once. No new routes yet, no dedup yet (Task 5), no gallery persistence yet (Task 6).

**Files:**
- Modify: `src/streamlinify/web/session.py`
- Modify: `src/streamlinify/web/routes_ingest.py`
- Modify: `src/streamlinify/app.py`
- Modify: `tests/web/test_ingest_routes.py` (updated response expectations)
- Test: add cases to `tests/web/test_ingest_routes.py`

**Interfaces:**
- Consumes: `WorkspaceRegistry` (Task 2), `ArchiveState` (Task 3), `display_name` (Task 1).
- Produces:
  - `Session` gains fields `workspace_id: str`, `state_dir: Path`, `archive: ArchiveState`.
  - `create_app()` sets `app.state.registry = WorkspaceRegistry(settings.workspace_dir / "workspaces.json")`.
  - `_start_session(request, export_root, *, managed: bool) -> dict` — return dict now includes `workspace_id` and `display_name`.
  - `_apply_archive(inventory, ids: set[str]) -> None`, `_maybe_adopt_legacy_state(state_dir: Path) -> None` (module-level helpers in `routes_ingest.py`).
  - `GET /api/session` returns `{loaded, export_name, workspace_id, display_name}`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/web/test_ingest_routes.py` (and update the two existing exact-equality assertions noted in Step 5):
```python
import json as _json


def test_ingest_folder_writes_per_workspace_state(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())

    resp = client.post("/api/ingest/folder", json={"folder": str(export_root)})
    body = resp.json()

    assert body["ok"] is True
    assert body["workspace_id"] == "export"
    assert body["display_name"] == "export"          # no date -> raw name
    # Per-workspace state dir is created under workspace/state/<id>/
    state_dir = tmp_path / "workspace" / "state" / "export"
    assert state_dir.is_dir()
    # The registry file exists and records this workspace.
    reg = _json.loads((tmp_path / "workspace" / "workspaces.json").read_text())
    assert reg["last_active"] == "export"
    assert any(w["id"] == "export" for w in reg["workspaces"])


def test_two_exports_keep_separate_selection(export_root, video_export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())

    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    client.post("/api/toggle", json={"album_fbid": "111", "photo_fbid": "a01"})

    # Switch to the other export by ingesting it; first export's selection must not leak.
    client.post("/api/ingest/folder", json={"folder": str(video_export_root)})
    sel_a = tmp_path / "workspace" / "state" / "export" / "selection.json"
    sel_b = tmp_path / "workspace" / "state" / "video_export" / "selection.json"
    assert sel_a.exists()                    # first workspace kept its own file
    assert not sel_b.exists() or _json.loads(sel_b.read_text()) == {}


def test_session_status_includes_display_name(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})

    status = client.get("/api/session").json()
    assert status == {
        "loaded": True,
        "export_name": "export",
        "workspace_id": "export",
        "display_name": "export",
    }


def test_legacy_flat_state_adopted_into_first_workspace(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "renames.json").write_text(_json.dumps({"111": "My Custom Name"}), encoding="utf-8")

    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})

    moved = ws / "state" / "export" / "renames.json"
    assert moved.exists()
    assert _json.loads(moved.read_text()) == {"111": "My Custom Name"}
    assert not (ws / "renames.json").exists()        # moved, not copied
    assert (ws / ".migrated").exists()
```

Note: album fbid `111` is `Animo Fest` in the `export_root` fixture (`AnimoFest_111`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest -q tests/web/test_ingest_routes.py -k "per_workspace or separate_selection or display_name or legacy"`
Expected: FAIL (`KeyError: 'workspace_id'` / missing state dir / missing `.migrated`).

- [ ] **Step 3: Update `session.py`**

Replace `src/streamlinify/web/session.py` with:
```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..inventory.models import ExportInventory
from ..inventory.renames import RenameState
from ..selection.archive_state import ArchiveState
from ..selection.state import SelectionState
from ..thumbnails.service import ThumbnailService
from ..thumbnails.video_store import VideoThumbnailStore


@dataclass
class Session:
    workspace_id: str
    state_dir: Path
    export_root: Path
    inventory: ExportInventory
    selection: SelectionState
    thumbnails: ThumbnailService
    video_thumbs: VideoThumbnailStore
    renames: RenameState
    archive: ArchiveState
```

- [ ] **Step 4: Update `app.py` to hold the registry**

In `src/streamlinify/app.py`, add the import and initialize `app.state.registry`. Change the top of `create_app`:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .web.registry import WorkspaceRegistry


def create_app() -> FastAPI:
    app = FastAPI(title="Streamlinify")
    app.state.session = None
    app.state.registry = WorkspaceRegistry(settings.workspace_dir / "workspaces.json")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    ...
```
(Leave the router includes below unchanged for now — the workspaces router is added in Task 5.)

- [ ] **Step 5: Rewrite `routes_ingest.py`**

Replace the imports block and the `session_status` / `_start_session` / ingest functions. Full new `src/streamlinify/web/routes_ingest.py`:
```python
from __future__ import annotations

import shutil
import subprocess
import time
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from ..config import settings
from ..ingest.browse import list_directory
from ..ingest.unzip import extract_zip
from ..ingest.validate import find_export_root, validate_export
from ..inventory.models import ExportInventory
from ..inventory.naming import display_name
from ..inventory.parser import build_inventory
from ..inventory.renames import RenameState
from ..selection.archive_state import ArchiveState
from ..selection.policy import DefaultPolicy
from ..selection.state import SelectionState
from ..thumbnails.service import ThumbnailService
from ..thumbnails.video_store import VideoThumbnailStore
from .session import Session

router = APIRouter()


class FolderRequest(BaseModel):
    folder: str


class ZipRequest(BaseModel):
    path: str


@router.get("/")
def health() -> dict:
    return {"name": "streamlinify", "status": "ok"}


@router.get("/api/session")
def session_status(request: Request) -> dict:
    session = request.app.state.session
    if session is None:
        return {"loaded": False, "export_name": None}
    return {
        "loaded": True,
        "export_name": session.export_root.name,
        "workspace_id": session.workspace_id,
        "display_name": display_name(session.workspace_id),
    }


def _apply_archive(inventory: ExportInventory, ids: set[str]) -> None:
    """Move albums whose fbid is in ``ids`` out of ``albums`` into ``archived_albums``.

    Restores the user's persisted album-archive decisions at session-build time,
    matching what ``POST /api/album/archive`` does at runtime. Order preserved.
    """
    if not ids:
        return
    to_archive = [a for a in inventory.albums if a.fb_album_id in ids]
    if not to_archive:
        return
    inventory.albums = [a for a in inventory.albums if a.fb_album_id not in ids]
    inventory.archived_albums.extend(to_archive)


def _maybe_adopt_legacy_state(state_dir: Path) -> None:
    """One-time: move pre-multi-workspace flat state into the first workspace.

    Before this feature, ``selection.json`` / ``renames.json`` lived directly in
    ``workspace/``. On the first workspace opened after upgrade, adopt them so the
    volunteer doesn't lose in-progress work. Guarded by a ``.migrated`` marker so
    it never runs twice; skipped if this workspace already has a state dir.
    """
    ws = settings.workspace_dir
    marker = ws / ".migrated"
    if marker.exists() or state_dir.exists():
        return
    state_dir.mkdir(parents=True, exist_ok=True)
    for name in ("selection.json", "renames.json"):
        legacy = ws / name
        if legacy.exists():
            shutil.move(str(legacy), str(state_dir / name))
    marker.write_text("1", encoding="utf-8")


def _start_session(request: Request, export_root: Path, *, managed: bool) -> dict:
    report = validate_export(export_root)
    if not report.ok:
        return {"ok": False, "errors": list(report.missing)}

    registry = request.app.state.registry
    entry = registry.register(export_root, managed=managed, now=time.time())
    state_dir = settings.workspace_dir / "state" / entry.id
    _maybe_adopt_legacy_state(state_dir)

    inventory = build_inventory(export_root)
    renames = RenameState(state_dir / "renames.json")
    archive = ArchiveState(state_dir / "archive.json")
    for album in inventory.albums + inventory.archived_albums:
        album.original_name = album.name
        if album.fb_album_id in renames._renames:
            album.name = renames._renames[album.fb_album_id]
    _apply_archive(inventory, archive.archived_ids())

    request.app.state.session = Session(
        workspace_id=entry.id,
        state_dir=state_dir,
        export_root=export_root,
        inventory=inventory,
        selection=SelectionState(state_dir / "selection.json", DefaultPolicy()),
        thumbnails=ThumbnailService(state_dir / "thumbs"),
        video_thumbs=VideoThumbnailStore(state_dir / "thumbs" / "videos"),
        renames=renames,
        archive=archive,
    )
    return {
        "ok": True,
        "errors": [],
        "export_name": export_root.name,
        "workspace_id": entry.id,
        "display_name": entry.display_name,
    }


@router.get("/api/browse")
def browse(path: str | None = None) -> dict:
    """List sub-directories of `path` (defaults to home) for the folder picker."""
    try:
        return list_directory(Path(path) if path else None)
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(status_code=400, detail=f"Cannot open folder: {exc}") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=f"Permission denied: {exc}") from exc


@router.post("/api/ingest/folder")
def ingest_folder(request: Request, body: FolderRequest) -> dict:
    return _start_session(request, find_export_root(Path(body.folder)), managed=False)


@router.post("/api/ingest/zip")
def ingest_zip(request: Request, body: ZipRequest) -> dict:
    """Unzip a `.zip` already on this machine into workspace/imports/<stem>/.

    Dedup: if that folder already exists we skip extraction and just open it.
    """
    src = Path(body.path).expanduser()
    if not src.is_file() or src.suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="Not a .zip file on this computer")
    dest = settings.workspace_dir / "imports" / src.stem
    deduped = dest.exists()
    if not deduped:
        try:
            extract_zip(src, dest)
        except (zipfile.BadZipFile, ValueError, subprocess.CalledProcessError) as exc:
            raise HTTPException(status_code=400, detail=f"Could not unzip that archive: {exc}") from exc
    result = _start_session(request, find_export_root(dest), managed=True)
    result["deduped"] = deduped
    return result


@router.post("/api/ingest/upload")
def ingest_upload(request: Request, file: UploadFile = File(...)) -> dict:
    workspace = settings.workspace_dir
    import_dir = workspace / "import"
    import_dir.mkdir(parents=True, exist_ok=True)
    zip_path = import_dir / (file.filename or "export.zip")
    dest = workspace / "imports" / Path(zip_path.name).stem
    try:
        with zip_path.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        if not dest.exists():
            extract_zip(zip_path, dest)
    finally:
        zip_path.unlink(missing_ok=True)
    return _start_session(request, find_export_root(dest), managed=True)
```

- [ ] **Step 6: Update the two existing exact-equality assertions**

In `tests/web/test_ingest_routes.py`, the existing tests assert full dict equality on the ingest response and `/api/session`. Update them:

- `test_ingest_zip_ok`: change
  ```python
  assert resp.json() == {"ok": True, "errors": [], "export_name": "export"}
  assert client.get("/api/session").json() == {"loaded": True, "export_name": "export"}
  ```
  to
  ```python
  body = resp.json()
  assert body["ok"] is True and body["export_name"] == "export"
  assert body["workspace_id"] == "export" and body["deduped"] is False
  status = client.get("/api/session").json()
  assert status["loaded"] is True and status["display_name"] == "export"
  ```
- Any other test asserting the exact ingest/`/api/session` dict: relax to key checks the same way. Search the file for `"export_name": "export"}` and update each.

- [ ] **Step 7: Run tests to verify they pass**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest -q tests/web/test_ingest_routes.py`
Expected: PASS (all ingest tests).

- [ ] **Step 8: Run the full backend suite (guard against regressions)**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest -q`
Expected: PASS. If `tests/web/test_gallery_routes.py` or others construct a `Session` directly, they'll fail on the new required fields — those are fixed in Task 6; if any unrelated test builds `Session` manually, update it to pass `workspace_id="export"`, `state_dir=tmp_path`, `archive=ArchiveState(tmp_path/"archive.json")`.

- [ ] **Step 9: Commit**

```bash
git add src/streamlinify/web/session.py src/streamlinify/web/routes_ingest.py src/streamlinify/app.py tests/web/test_ingest_routes.py
git commit -m "feat: workspace-aware session with per-workspace state dirs and legacy migration"
```

---

### Task 5: Workspaces API (`web/routes_workspaces.py`)

**Files:**
- Create: `src/streamlinify/web/routes_workspaces.py`
- Modify: `src/streamlinify/app.py` (include the router)
- Test: `tests/web/test_routes_workspaces.py`

**Interfaces:**
- Consumes: `_start_session` from `routes_ingest` (Task 4), `app.state.registry`.
- Produces:
  - `GET /api/workspaces` → `{"workspaces": [{id, display_name, raw_name, last_opened_ts, managed}], "last_active": id|null}`
  - `POST /api/workspaces/open` `{id}` → same dict shape as `_start_session`; 404 unknown id; 410 if the export root no longer exists on disk.
  - `POST /api/workspaces/remove` `{id, delete_files: bool}` → `{ok: true, deleted_files: bool}`; deletes files only for `managed` workspaces, verifying removal.

- [ ] **Step 1: Write the failing test**

`tests/web/test_routes_workspaces.py`:
```python
from pathlib import Path

from fastapi.testclient import TestClient

from streamlinify.app import create_app


def test_list_and_open_workspace(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})

    listing = client.get("/api/workspaces").json()
    assert listing["last_active"] == "export"
    assert listing["workspaces"][0]["id"] == "export"
    assert listing["workspaces"][0]["display_name"] == "export"

    # Drop the live session, then reopen via the registry.
    client.app.state.session = None
    resp = client.post("/api/workspaces/open", json={"id": "export"})
    assert resp.status_code == 200
    assert resp.json()["workspace_id"] == "export"
    assert client.get("/api/session").json()["loaded"] is True


def test_open_unknown_returns_404(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    resp = client.post("/api/workspaces/open", json={"id": "nope"})
    assert resp.status_code == 404


def test_open_missing_root_returns_410(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    # Simulate the export folder being moved/deleted out-of-band.
    import shutil
    shutil.rmtree(export_root)
    resp = client.post("/api/workspaces/open", json={"id": "export"})
    assert resp.status_code == 410


def test_remove_managed_deletes_files_and_state(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Managed workspace: copy the export under workspace/imports/<id>/ so removal deletes it.
    import shutil
    imports = tmp_path / "workspace" / "imports" / "myexport"
    shutil.copytree(export_root, imports / "export")
    client = TestClient(create_app())
    # Register it as managed by ingesting from the imports tree via folder ingest is external;
    # instead open through the zip-less managed path: register directly.
    client.app.state.registry.register(imports / "export", managed=True, now=1.0)

    state_dir = tmp_path / "workspace" / "state" / "export"
    state_dir.mkdir(parents=True)
    (state_dir / "selection.json").write_text("{}", encoding="utf-8")

    resp = client.post("/api/workspaces/remove", json={"id": "export", "delete_files": True})
    assert resp.status_code == 200
    assert resp.json()["deleted_files"] is True
    assert not (imports / "export").exists()
    assert not state_dir.exists()
    assert client.app.state.registry.get("export") is None


def test_remove_external_keeps_files(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})  # external (managed=False)

    resp = client.post("/api/workspaces/remove", json={"id": "export", "delete_files": True})
    assert resp.status_code == 200
    assert resp.json()["deleted_files"] is False   # external files never deleted
    assert export_root.exists()
    assert client.app.state.registry.get("export") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest -q tests/web/test_routes_workspaces.py`
Expected: FAIL with 404 on `/api/workspaces` (router not mounted).

- [ ] **Step 3: Write the router**

`src/streamlinify/web/routes_workspaces.py`:
```python
from __future__ import annotations

import shutil
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..config import settings
from .routes_ingest import _start_session

router = APIRouter()


class OpenRequest(BaseModel):
    id: str


class RemoveRequest(BaseModel):
    id: str
    delete_files: bool = False


@router.get("/api/workspaces")
def list_workspaces(request: Request) -> dict:
    registry = request.app.state.registry
    return {
        "workspaces": [
            {
                "id": e.id,
                "display_name": e.display_name,
                "raw_name": Path(e.export_root).name,
                "last_opened_ts": e.last_opened_ts,
                "managed": e.managed,
            }
            for e in registry.list()
        ],
        "last_active": registry.last_active,
    }


@router.post("/api/workspaces/open")
def open_workspace(request: Request, body: OpenRequest) -> dict:
    registry = request.app.state.registry
    entry = registry.get(body.id)
    if entry is None:
        raise HTTPException(status_code=404, detail="No such workspace")
    root = Path(entry.export_root)
    if not root.exists():
        raise HTTPException(status_code=410, detail="Workspace files are missing")
    return _start_session(request, root, managed=entry.managed)


def _remove_tree(path: Path, attempts: int = 5) -> bool:
    """Delete a directory tree, tolerating Windows file locks. Returns True iff gone."""
    for _ in range(attempts):
        if not path.exists():
            return True
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return True
        time.sleep(0.2)
    return not path.exists()


@router.post("/api/workspaces/remove")
def remove_workspace(request: Request, body: RemoveRequest) -> dict:
    registry = request.app.state.registry
    entry = registry.get(body.id)
    if entry is None:
        raise HTTPException(status_code=404, detail="No such workspace")

    deleted_files = False
    if body.delete_files and entry.managed:
        # Managed workspaces were unzipped under workspace/imports/<stem>/. Delete the
        # extraction folder (the direct child of imports/) plus the state dir. Guard so
        # we NEVER rmtree anything outside imports/, even if export_root is unexpected.
        root = Path(entry.export_root).resolve()
        imports_base = (settings.workspace_dir / "imports").resolve()
        state_dir = settings.workspace_dir / "state" / entry.id
        ok_state = _remove_tree(state_dir)
        ok_import = True
        if imports_base in root.parents:
            import_child = root
            while import_child.parent != imports_base:
                import_child = import_child.parent
            ok_import = _remove_tree(import_child)
        if not (ok_import and ok_state):
            raise HTTPException(
                status_code=500,
                detail="Could not delete all files (they may be open in another program). "
                "The workspace was kept in the list.",
            )
        deleted_files = True

    # Clear the live session if it was this workspace.
    session = request.app.state.session
    if session is not None and session.workspace_id == body.id:
        request.app.state.session = None

    registry.remove(body.id)
    return {"ok": True, "deleted_files": deleted_files}
```

- [ ] **Step 4: Mount the router in `app.py`**

In `src/streamlinify/app.py`, add to the import group and include list:
```python
    from .web.routes_build import router as build_router
    from .web.routes_gallery import router as gallery_router
    from .web.routes_ingest import router as ingest_router
    from .web.routes_video import router as video_router
    from .web.routes_workspaces import router as workspaces_router

    app.include_router(ingest_router)
    app.include_router(workspaces_router)
    app.include_router(gallery_router)
    app.include_router(video_router)
    app.include_router(build_router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest -q tests/web/test_routes_workspaces.py`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add src/streamlinify/web/routes_workspaces.py src/streamlinify/app.py tests/web/test_routes_workspaces.py
git commit -m "feat: /api/workspaces list, open, and remove endpoints"
```

---

### Task 6: Persist album archive on mutate (`routes_gallery.py`)

**Files:**
- Modify: `src/streamlinify/web/routes_gallery.py:178-218`
- Test: add to `tests/web/test_gallery_routes.py`

**Interfaces:**
- Consumes: `session.archive` (Task 4).
- Produces: no signature change — `/api/album/archive` and `/api/album/unarchive` now call `session.archive.add(...)` / `.remove(...)`.

- [ ] **Step 1: Write the failing test**

Add to `tests/web/test_gallery_routes.py`:
```python
import json
from pathlib import Path

from fastapi.testclient import TestClient

from streamlinify.app import create_app


def test_archive_persists_and_restores_on_reopen(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})

    # Archive album 111 (Animo Fest).
    resp = client.post("/api/album/archive", json={"album_fbid": "111"})
    assert resp.status_code == 200

    archive_file = tmp_path / "workspace" / "state" / "export" / "archive.json"
    assert json.loads(archive_file.read_text()) == ["111"]

    # Reopen the workspace: album 111 must come back as archived, not as a normal album.
    client.app.state.session = None
    client.post("/api/workspaces/open", json={"id": "export"})
    inv = client.get("/api/inventory").json()
    assert all(a["fb_album_id"] != "111" for a in inv["albums"])
    assert any(a["fb_album_id"] == "111" for a in inv["archived_albums"])


def test_unarchive_updates_persisted_state(export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    client.post("/api/album/archive", json={"album_fbid": "111"})
    client.post("/api/album/unarchive", json={"album_fbid": "111"})

    archive_file = tmp_path / "workspace" / "state" / "export" / "archive.json"
    assert json.loads(archive_file.read_text()) == []
```

(Confirm the album fbid: in `export_root`, `Animo Fest` lives in dir `AnimoFest_111`, so its `fb_album_id` is `111`. If a serializer test in this file already asserts album ids, reuse that value.)

- [ ] **Step 2: Run test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest -q tests/web/test_gallery_routes.py -k "archive"`
Expected: FAIL — `archive.json` not written (`FileNotFoundError`).

- [ ] **Step 3: Add persistence to the archive routes**

In `src/streamlinify/web/routes_gallery.py`, in `archive_album`, after `inv.archived_albums.append(album)` (currently line ~193) add:
```python
    session.archive.add(body.album_fbid)
```
In `unarchive_album`, after `inv.albums.append(album)` (currently line ~215) add:
```python
    session.archive.remove(body.album_fbid)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest -q tests/web/test_gallery_routes.py -k "archive"`
Expected: PASS (2 passed).

- [ ] **Step 5: Run full backend suite + lint**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest -q && uv run ruff check .`
Expected: PASS, no lint errors.

- [ ] **Step 6: Commit**

```bash
git add src/streamlinify/web/routes_gallery.py tests/web/test_gallery_routes.py
git commit -m "feat: persist album archive/unarchive so it survives reload"
```

---

### Task 7: Frontend API client (`lib/api.js`)

**Files:**
- Modify: `frontend/src/lib/api.js` (add three functions before the final `export { API_BASE };`)

**Interfaces:**
- Produces: `listWorkspaces(fetchFn?)`, `openWorkspace(id, fetchFn?)`, `removeWorkspace(id, deleteFiles, fetchFn?)`.

- [ ] **Step 1: Add the functions**

Insert into `frontend/src/lib/api.js` immediately before `export { API_BASE };`:
```javascript
/** List every known workspace, newest-opened first, plus the last-active id. */
export async function listWorkspaces(fetchFn = fetch) {
	try {
		const res = await fetchFn(url('/api/workspaces'));
		if (!res.ok) return { workspaces: [], last_active: null };
		return res.json();
	} catch {
		return { workspaces: [], last_active: null };
	}
}

/** Open a workspace by id, rebuilding its session (restores its saved state). */
export async function openWorkspace(id, fetchFn = fetch) {
	try {
		const res = await fetchFn(url('/api/workspaces/open'), {
			method: 'POST',
			headers: jsonHeaders,
			body: JSON.stringify({ id })
		});
		if (!res.ok) {
			const data = await res.json().catch(() => ({}));
			return { ok: false, error: data.detail ?? 'Could not open that workspace.' };
		}
		return res.json();
	} catch {
		return { ok: false, error: UNREACHABLE };
	}
}

/** Remove a workspace from the list; optionally delete its files (managed only). */
export async function removeWorkspace(id, deleteFiles, fetchFn = fetch) {
	try {
		const res = await fetchFn(url('/api/workspaces/remove'), {
			method: 'POST',
			headers: jsonHeaders,
			body: JSON.stringify({ id, delete_files: deleteFiles })
		});
		if (!res.ok) {
			const data = await res.json().catch(() => ({}));
			return { ok: false, error: data.detail ?? 'Could not remove that workspace.' };
		}
		return res.json();
	} catch {
		return { ok: false, error: UNREACHABLE };
	}
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/api.js
git commit -m "feat(ui): api client for workspace list/open/remove"
```

---

### Task 8: WorkspaceList component (`lib/components/WorkspaceList.svelte`)

A list of workspace cards. Clicking a card calls `onOpen(id)`. The remove control requires a **two-step confirmation** (click "Remove" → the card reveals a confirm row showing what will be deleted → click "Delete permanently") before calling `onRemove(id, deleteFiles)`.

**Files:**
- Create: `frontend/src/lib/components/WorkspaceList.svelte`
- Test: `frontend/src/lib/components/WorkspaceList.test.js`

**Interfaces:**
- Props: `workspaces: Array<{id, display_name, raw_name, last_opened_ts, managed}>`, `onOpen: (id) => void`, `onRemove: (id, deleteFiles) => void`.

- [ ] **Step 1: Write the failing test**

`frontend/src/lib/components/WorkspaceList.test.js`:
```javascript
import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import WorkspaceList from './WorkspaceList.svelte';

const WS = [
	{ id: 'w1', display_name: 'Archers Network Facebook Export | 2026-07-03', raw_name: 'facebook-...-7xOuGnNl', last_opened_ts: 2, managed: true },
	{ id: 'w2', display_name: 'Archers Network Facebook Export | 2026-06-08', raw_name: 'facebook-...-Th2bzEER', last_opened_ts: 1, managed: false }
];

describe('WorkspaceList', () => {
	it('renders a card per workspace with its display name', () => {
		render(WorkspaceList, { workspaces: WS, onOpen: () => {}, onRemove: () => {} });
		expect(screen.getByText('Archers Network Facebook Export | 2026-07-03')).toBeTruthy();
		expect(screen.getByText('Archers Network Facebook Export | 2026-06-08')).toBeTruthy();
	});

	it('calls onOpen with the id when a card is clicked', async () => {
		const onOpen = vi.fn();
		render(WorkspaceList, { workspaces: WS, onOpen, onRemove: () => {} });
		await fireEvent.click(screen.getByText('Archers Network Facebook Export | 2026-07-03'));
		expect(onOpen).toHaveBeenCalledWith('w1');
	});

	it('requires two steps before calling onRemove', async () => {
		const onRemove = vi.fn();
		render(WorkspaceList, { workspaces: [WS[0]], onOpen: () => {}, onRemove });

		await fireEvent.click(screen.getByRole('button', { name: /remove/i }));
		expect(onRemove).not.toHaveBeenCalled();                 // first click only reveals confirm

		await fireEvent.click(screen.getByRole('button', { name: /delete permanently/i }));
		expect(onRemove).toHaveBeenCalledWith('w1', true);       // managed -> delete files
	});
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- src/lib/components/WorkspaceList.test.js`
Expected: FAIL — component file does not exist.

- [ ] **Step 3: Write the component**

`frontend/src/lib/components/WorkspaceList.svelte`:
```svelte
<script>
	let { workspaces = [], onOpen, onRemove } = $props();
	// id of the card currently showing its delete-confirm row, or null.
	let confirmingId = $state(null);

	function fmt(ts) {
		if (!ts) return '';
		try {
			return new Intl.DateTimeFormat('en-US', {
				month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'
			}).format(new Date(ts * 1000));
		} catch {
			return '';
		}
	}
</script>

<ul class="space-y-2">
	{#each workspaces as ws (ws.id)}
		<li class="rounded-xl border border-surface-300 bg-surface-50 shadow-sm">
			<div class="flex items-center gap-3 p-3">
				<button
					type="button"
					class="min-w-0 flex-1 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
					onclick={() => onOpen(ws.id)}
				>
					<p class="truncate font-medium text-surface-900">{ws.display_name}</p>
					<p class="truncate text-xs text-surface-500" title={ws.raw_name}>
						{ws.raw_name}{#if ws.last_opened_ts} · opened {fmt(ws.last_opened_ts)}{/if}
					</p>
				</button>
				{#if confirmingId !== ws.id}
					<button
						type="button"
						class="shrink-0 rounded-lg px-2.5 py-1.5 text-sm font-medium text-surface-500 transition-colors hover:bg-error-50 hover:text-error-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-error-600"
						onclick={() => (confirmingId = ws.id)}
					>
						Remove
					</button>
				{/if}
			</div>

			{#if confirmingId === ws.id}
				<div class="border-t border-error-200 bg-error-50 p-3" role="alertdialog" aria-live="polite">
					<p class="text-sm text-error-800">
						{#if ws.managed}
							This permanently deletes the unzipped export and all saved selections for
							<span class="font-medium">{ws.display_name}</span>. This cannot be undone.
						{:else}
							This removes <span class="font-medium">{ws.display_name}</span> from the list.
							Its files on disk are left untouched.
						{/if}
					</p>
					<div class="mt-2 flex gap-2">
						<button
							type="button"
							class="rounded-lg bg-error-700 px-3 py-1.5 text-sm font-semibold text-error-50 transition-colors hover:bg-error-800"
							onclick={() => { onRemove(ws.id, ws.managed); confirmingId = null; }}
						>
							{ws.managed ? 'Delete permanently' : 'Remove from list'}
						</button>
						<button
							type="button"
							class="rounded-lg border border-surface-300 bg-surface-50 px-3 py-1.5 text-sm font-medium text-surface-700 transition-colors hover:bg-surface-100"
							onclick={() => (confirmingId = null)}
						>
							Cancel
						</button>
					</div>
				</div>
			{/if}
		</li>
	{/each}
</ul>
```

Note: the test's `/delete permanently/i` matches the managed button label; for an external workspace the label is "Remove from list" and `onRemove` is called with `false`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test -- src/lib/components/WorkspaceList.test.js`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/components/WorkspaceList.svelte frontend/src/lib/components/WorkspaceList.test.js
git commit -m "feat(ui): WorkspaceList with two-step remove confirmation"
```

---

### Task 9: Landing page — workspace picker + auto-resume (`routes/+page.svelte`)

**Files:**
- Modify: `frontend/src/routes/+page.svelte`

**Interfaces:**
- Consumes: `listWorkspaces`, `openWorkspace`, `removeWorkspace` (Task 7); `WorkspaceList` (Task 8).

- [ ] **Step 1: Add imports and state to the `<script>` block**

In `frontend/src/routes/+page.svelte`, extend the imports (top of `<script>`):
```javascript
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { ingestFolder, ingestUpload, ingestZip, listWorkspaces, openWorkspace, removeWorkspace } from '$lib/api.js';
	import FolderPicker from '$lib/components/FolderPicker.svelte';
	import WorkspaceList from '$lib/components/WorkspaceList.svelte';
```
Add state alongside the existing `let busy = ...` declarations:
```javascript
	let workspaces = $state([]);
	let resolving = $state(true); // true while deciding auto-resume vs. show list
```

- [ ] **Step 2: Add the auto-resume + list-load logic**

Add after the existing `handle(...)` function in the `<script>`:
```javascript
	onMount(async () => {
		const switching = new URLSearchParams(window.location.search).get('switch') === '1';
		const data = await listWorkspaces();
		workspaces = data.workspaces ?? [];
		if (!switching && data.last_active) {
			const result = await openWorkspace(data.last_active);
			if (result.ok) {
				await goto('/gallery');
				return;
			}
		}
		resolving = false;
	});

	async function openWs(id) {
		busy = true;
		busyLabel = 'Opening workspace…';
		const result = await openWorkspace(id);
		busy = false;
		if (result.ok) await goto('/gallery');
		else errors = [result.error ?? 'Could not open that workspace.'];
	}

	async function removeWs(id, deleteFiles) {
		const result = await removeWorkspace(id, deleteFiles);
		if (result.ok) {
			workspaces = workspaces.filter((w) => w.id !== id);
		} else {
			errors = [result.error ?? 'Could not remove that workspace.'];
		}
	}
```

- [ ] **Step 3: Render the workspace list above the ingest UI**

In the template, immediately after `<section class="mx-auto max-w-2xl">` and before the existing header `<div class="mb-6">`, insert:
```svelte
	{#if resolving}
		<div class="flex items-center justify-center py-16" aria-live="polite">
			<span class="size-8 animate-spin rounded-full border-[3px] border-primary-200 border-t-primary-600" aria-hidden="true"></span>
		</div>
	{:else}
		{#if workspaces.length}
			<div class="mb-8">
				<h2 class="mb-3 text-lg font-semibold tracking-tight text-surface-900">Your workspaces</h2>
				<WorkspaceList {workspaces} onOpen={openWs} onRemove={removeWs} />
			</div>
			<div class="my-6 flex items-center gap-3 text-xs font-medium tracking-wide text-surface-400">
				<span class="h-px flex-1 bg-surface-300"></span>
				OR ADD A NEW EXPORT
				<span class="h-px flex-1 bg-surface-300"></span>
			</div>
		{/if}
```
Then wrap the **existing** content (from `<div class="mb-6">` through the closing of the folder card, i.e. just before `<FolderPicker ... />`) so it only renders when not resolving. Close the `{:else}` branch with `{/if}` right before `<FolderPicker`:
```svelte
	{/if}

	<FolderPicker
		...
	/>
```

Concretely: the `{:else}` opened in the inserted block stays open across the existing markup; add a single `{/if}` on the line directly above `<FolderPicker`. (The `FolderPicker` overlay stays outside the conditional so it can open regardless.)

- [ ] **Step 4: Verify the app builds and existing landing behavior is intact**

Run: `cd frontend && npm run build`
Expected: build succeeds with no Svelte compile errors.

Then, with both servers running (`UV_LINK_MODE=copy uv run streamlinify` and `cd frontend && npm run dev`), load `http://localhost:5173/?switch=1`:
- The workspace list renders (if any exist) with the ingest UI below.
- Clicking a card opens the gallery; the ingest drop-zone still works.
- Loading `http://localhost:5173/` (no `?switch`) with a last-active workspace jumps straight to the gallery.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/+page.svelte
git commit -m "feat(ui): landing workspace picker with auto-resume of last-active"
```

---

### Task 10: Gallery — "Switch workspace" + active-workspace name (`routes/gallery/+page.svelte`, `+page.js`)

**Files:**
- Modify: `frontend/src/routes/gallery/+page.js`
- Modify: `frontend/src/routes/gallery/+page.svelte`

**Interfaces:**
- Consumes: `getSession` (existing) for the active workspace's `display_name`.

- [ ] **Step 1: Load the display name in `+page.js`**

Replace `frontend/src/routes/gallery/+page.js`:
```javascript
import { redirect } from '@sveltejs/kit';
import { getInventory, getSession } from '$lib/api.js';

export async function load({ fetch }) {
	const inventory = await getInventory(fetch);
	if (!inventory) throw redirect(307, '/');
	const session = await getSession(fetch);
	return { inventory, displayName: session?.display_name ?? '' };
}
```

- [ ] **Step 2: Add a "Switch workspace" control + name to the left rail**

In `frontend/src/routes/gallery/+page.svelte`, the left rail `<aside>` opens at line ~280. Immediately after the `<aside ...>` opening tag and before the `<div class="rounded-xl border ...">` album-list container, insert:
```svelte
		<div class="mb-2 flex shrink-0 items-center justify-between gap-2 px-1">
			<p class="min-w-0 truncate text-sm font-medium text-surface-700" title={data.displayName}>
				{data.displayName}
			</p>
			<a
				href="/?switch=1"
				class="shrink-0 rounded-lg border border-surface-300 bg-surface-50 px-2.5 py-1 text-xs font-medium text-surface-700 transition-colors hover:bg-surface-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
			>
				Switch
			</a>
		</div>
```
(`data` is already destructured via `let { data } = $props();` at the top of the component.)

- [ ] **Step 3: Verify build + behavior**

Run: `cd frontend && npm run build`
Expected: build succeeds.

With both servers running: open a workspace, confirm the active workspace name shows above the album list and the **Switch** link returns to the landing list (`/?switch=1`) without auto-resuming. From the landing list, opening another workspace shows its own selections/renames/archive.

- [ ] **Step 4: Run the full frontend test suite**

Run: `cd frontend && npm run test`
Expected: PASS (existing tests + the new `WorkspaceList` test).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/gallery/+page.js frontend/src/routes/gallery/+page.svelte
git commit -m "feat(ui): show active workspace and add Switch workspace control"
```

---

### Task 11: Full-stack verification pass

**Files:** none (verification only).

- [ ] **Step 1: Backend suite + lint**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest -q && uv run ruff check .`
Expected: all pass, no lint errors.

- [ ] **Step 2: Frontend suite + build**

Run: `cd frontend && npm run test && npm run build`
Expected: all pass, build succeeds.

- [ ] **Step 3: Manual end-to-end smoke (two workspaces)**

Kill any running dev server first (per project rule): `pwsh ./kill-server.ps1`. Then start both servers (`UV_LINK_MODE=copy uv run streamlinify`, `cd frontend && npm run dev`) and verify:
1. Ingest export A (folder or zip) → gallery opens; select a few photos in one album; rename an album; archive an album.
2. Click **Switch** → landing shows workspace A in the list. Ingest export B → gallery opens with a clean state (no A selections).
3. Switch back → open A → selections, rename, and archived album are all restored.
4. Re-ingest A's **same zip** → no re-extraction (fast), opens the existing workspace (`deduped: true`).
5. Reload `http://localhost:5173/` with no query → auto-resumes the last-active workspace straight into the gallery.
6. On the landing list, **Remove** a *managed* workspace with the two-step confirm → its `workspace/imports/<id>/` and `workspace/state/<id>/` are gone; the card disappears. Remove an *external* workspace → card disappears but its on-disk folder remains.

- [ ] **Step 4: Commit any final touch-ups**

```bash
git add -A
git commit -m "chore: multi-workspace verification fixes" || echo "nothing to commit"
```

---

## Notes for the implementer

- **Album fbid in the fixture:** `export_root`'s "Animo Fest" album is in dir `AnimoFest_111`, so its `fb_album_id` is `111`; "Café Night" is `222`. Use these in archive/selection tests.
- **`display_name("export")` returns `"export"`** (no date → raw fallback) — that's why the synthetic-fixture tests expect `display_name == "export"`.
- **Do not add uncapped-policy wiring** here — the current `_start_session` uses a bare `DefaultPolicy()`; preserve that to keep this feature's diff focused. (Uncapped albums are a separate concern.)
- **Windows deletes:** `_remove_tree` retries and verifies; if it can't remove files (open handles / Defender lock), the route returns 500 and keeps the registry entry rather than lying about success.
- **Two servers must run together** for manual checks (API :8000, UI :5173/:3000).
```
