# Multi-workspace support with per-workspace save state

**Date:** 2026-07-06
**Status:** Approved design — ready for implementation plan

## Problem

Streamlinify is single-workspace and its saved state is flat and global:

- `workspace/selection.json` (kept photos) and `workspace/renames.json` (album names) are
  **shared across every export** — loading a second export reuses the first's state files.
- **Archived albums are not persisted at all.** `inventory.archived_albums` lives only in
  memory (`web/routes_gallery.py`), so a reload or server restart silently loses all
  album-archive state.
- Zip extraction always targets **one fixed path** (`workspace/import/unzipped`), so a
  second zip overwrites the first.
- The landing page can only ingest a new export; there is no way to see or pick among
  exports already unzipped on disk.

The volunteer curates a **new export every week** (e.g.
`facebook-ArchersNetwork-2026-07-03-7xOuGnNl`,
`facebook-ArchersNetwork-2026-06-08-Th2bzEER_previous-week-posts`). They need to keep
several weeks' work side by side, switch between them, and have each one remember exactly
where they left off.

## Goals

- **Detect and list** every already-unzipped workspace on the landing page; let the user
  pick which to work on.
- **Per-workspace save state**: kept images, renamed albums, and archived albums persist
  independently per export and are restored on reopen/restart.
- **Persist album-archive state** (new — currently memory-only).
- **Friendly display name** derived from the export folder name:
  `facebook-ArchersNetwork-2026-07-03-7xOuGnNl` → `Archers Network Facebook Export | 2026-07-03`.
- **Dedup on ingest**: if the zip being extracted is already unzipped/registered, skip
  re-extraction and open the existing workspace.
- **Auto-resume** the last-active workspace on startup; a "Switch workspace" control
  returns to the picker.
- **Remove a workspace** (with a double confirmation), deleting its unzipped files + state
  for app-managed workspaces.

## Non-goals

- No copying/duplicating export media into per-workspace bundles — media is referenced in
  place (~875 MB each).
- No dedup by "semantic week" — dedup is by **exact export folder name**. A fresh download
  of the same week (new random suffix) is a distinct workspace.
- No editable/custom workspace display names — the derived name is authoritative (raw
  folder name shown on hover).
- No deletion of *externally-referenced* export folders (ones the user pointed at via the
  folder picker, living outside `workspace/`). Those are **remove-from-list only**.
- No change to `partition_archive` (news-tagged photos) — that is derived classification,
  not user save-state.

## Key decisions (resolved during brainstorming)

| Decision | Choice |
|---|---|
| Where unzipped workspaces live / are detected | **Managed folder + registry.** Zips extract to `workspace/imports/<name>/`; a registry records every ingested export (managed or externally-referenced). |
| Dedup key | **Exact export folder name.** |
| Display name | Strip `facebook-`, CamelCase-split page name, `… Facebook Export \| <YYYY-MM-DD>`; **drop** any trailing annotation. Raw name on hover. |
| Switching / resume | **Auto-resume last-active** into the gallery on startup; "Switch workspace" opens the picker (suppresses auto-resume). |
| Remove | **Double confirmation.** Managed workspaces: delete unzipped files + state. External-referenced: remove-from-list only (never delete a folder the app didn't create). |
| Legacy flat state | **One-time auto-adopt** into the first workspace opened after upgrade. |
| Media copies | **Reference in place**, never copy. |

## Definitions

**Workspace** — one Facebook export the user is curating, identified by its export-root
folder name (the `id`). Exact-name dedup guarantees the id is unique.

**Managed workspace** — one whose media was unzipped by the app into
`workspace/imports/<id>/` (`managed: true`). **External workspace** — one the user pointed
at via the folder picker, living elsewhere on disk (`managed: false`).

**State dir** — `workspace/state/<id>/`, holding that workspace's `selection.json`,
`renames.json`, `archive.json`, and thumbnail caches (`thumbs/`, `thumbs/videos/`).

**Display name** — the friendly label; see `inventory/naming.py`.

## Architecture

### 1. `inventory/naming.py` (new — pure, unit-tested)

Isolates the folder-name → display-name rule.

```python
def display_name(export_name: str) -> str: ...
```

- Strip a leading `facebook-` if present.
- Find the first `\d{4}-\d{2}-\d{2}` date. The **page name** is everything before it;
  the **date** is the match. Ignore everything after the date (random suffix + any
  `_annotation`).
- CamelCase-split the page name (`ArchersNetwork` → `Archers Network`): insert a space
  between a lowercase/digit and a following uppercase letter; collapse existing
  `-`/`_`/whitespace to single spaces; title-case-safe (don't mangle existing spacing).
- Return `f"{page} Facebook Export | {date}"`.
- **Fallback:** if no date is found, return the raw `export_name` unchanged.

Examples:
`facebook-ArchersNetwork-2026-07-03-7xOuGnNl` → `Archers Network Facebook Export | 2026-07-03`;
`facebook-ArchersNetwork-2026-06-08-Th2bzEER_previous-week-posts` → `Archers Network Facebook Export | 2026-06-08`.

### 2. `web/registry.py` (new — persisted state, mirrors `RenameState`)

Owns `workspace/workspaces.json`:

```json
{
  "last_active": "facebook-ArchersNetwork-2026-07-03-7xOuGnNl",
  "workspaces": [
    {
      "id": "facebook-ArchersNetwork-2026-07-03-7xOuGnNl",
      "export_root": "E:\\...\\workspace\\imports\\facebook-...-7xOuGnNl\\<root>",
      "display_name": "Archers Network Facebook Export | 2026-07-03",
      "managed": true,
      "created_ts": 1751760000,
      "last_opened_ts": 1751846400
    }
  ]
}
```

```python
class WorkspaceRegistry:
    def __init__(self, path: Path) -> None: ...
    def list(self) -> list[WorkspaceEntry]: ...        # sorted by last_opened_ts desc
    def get(self, ws_id: str) -> WorkspaceEntry | None: ...
    def register(self, export_root: Path, *, managed: bool) -> WorkspaceEntry: ...
    def touch(self, ws_id: str) -> None: ...           # updates last_opened_ts + last_active
    def remove(self, ws_id: str) -> WorkspaceEntry | None: ...
    @property
    def last_active(self) -> str | None: ...
```

- `id` = `export_root.name`. `register` is idempotent on `id` (re-register updates the
  path/`last_opened_ts`, does not duplicate).
- `display_name` computed via `naming.display_name(id)` at register time and stored.
- Timestamps are supplied by the caller (route layer) — the registry does not call
  `time.time()` itself, so it stays trivially testable.

### 3. `web/session.py`

`Session` gains identity + a state dir so every persisted artifact is per-workspace:

```python
@dataclass
class Session:
    workspace_id: str
    state_dir: Path            # workspace/state/<id>/
    export_root: Path
    inventory: ExportInventory
    selection: SelectionState
    thumbnails: ThumbnailService
    video_thumbs: VideoThumbnailStore
    renames: RenameState
    archive: ArchiveState      # NEW
```

### 4. `selection/archive_state.py` (new — persisted, mirrors `RenameState`)

Persists user-driven album archiving (the piece that is memory-only today).

```python
class ArchiveState:
    def __init__(self, path: Path) -> None: ...   # workspace/state/<id>/archive.json
    def archived_ids(self) -> set[str]: ...
    def add(self, album_fbid: str) -> None: ...   # persists
    def remove(self, album_fbid: str) -> None: ...# persists
    def is_archived(self, album_fbid: str) -> bool: ...
```

`archive.json` = a JSON array of archived album fbids.

### 5. `web/routes_ingest.py` — session build, ingest, dedup

`_start_session(export_root, *, managed)` becomes workspace-aware:

```python
entry = registry.register(export_root, managed=managed)   # id = export_root.name
state_dir = settings.workspace_dir / "state" / entry.id
_maybe_adopt_legacy_state(state_dir)                       # §9 one-time migration
inventory = build_inventory(export_root)
renames = RenameState(state_dir / "renames.json")
archive = ArchiveState(state_dir / "archive.json")
for album in inventory.albums + inventory.archived_albums:
    album.original_name = album.name
    if album.fb_album_id in renames._renames:
        album.name = renames._renames[album.fb_album_id]
# Re-apply persisted album-archive: move archived albums out of inventory.albums.
_apply_archive(inventory, archive.archived_ids())
uncapped = frozenset(a.fb_album_id for a in inventory.albums if a.uncapped)
request.app.state.session = Session(
    workspace_id=entry.id, state_dir=state_dir, export_root=export_root,
    inventory=inventory,
    selection=SelectionState(state_dir / "selection.json",
                             DefaultPolicy(uncapped_albums=uncapped)),
    thumbnails=ThumbnailService(state_dir / "thumbs"),
    video_thumbs=VideoThumbnailStore(state_dir / "thumbs" / "videos"),
    renames=renames, archive=archive)
registry.touch(entry.id)
```

`_apply_archive(inventory, ids)` moves each album in `inventory.albums` whose
`fb_album_id ∈ ids` into `inventory.archived_albums` (order preserved), matching what the
`/api/album/archive` route does at runtime.

**Ingest routes** (`ingest_folder`, `ingest_zip`, `ingest_upload`):

- Extraction target for `ingest_zip`/`ingest_upload` changes from
  `workspace/import/unzipped` to `workspace/imports/<zip-stem>/`.
- **Dedup pre-check** (`ingest_zip`): if `workspace/imports/<zip-stem>/` exists **and** a
  registry entry for `<zip-stem>` (or the export root inside it) exists, **skip extraction**
  and open the existing workspace. Return a flag so the UI can note "already imported".
- `ingest_folder`: `find_export_root`, then `_start_session(root, managed=False)`.
  Re-picking an already-registered folder just re-opens it.
- The registry is stored on `app.state` (`create_app` initializes
  `app.state.registry = WorkspaceRegistry(settings.workspace_dir / "workspaces.json")`).

### 6. `web/routes_workspaces.py` (new router)

```
GET  /api/workspaces              -> {"workspaces": [ {id, display_name, raw_name,
                                       last_opened_ts, managed} ], "last_active": id|null}
POST /api/workspaces/open  {id}   -> builds the session for <id>; 404 if unknown / root
                                     missing on disk. Returns the same shape as ingest.
POST /api/workspaces/remove {id, delete_files: bool}
                                  -> unregister; if delete_files AND managed, rmtree the
                                     unzipped folder + state dir, VERIFYING deletion and
                                     retrying/​reporting on Windows lock errors
                                     (PermissionError / WinError 32). For external
                                     workspaces delete_files is ignored (list-only).
```

`open` verifies `export_root` still exists on disk; if the folder was moved/deleted
out-of-band it returns an error so the UI can offer to remove the stale entry.

### 7. `web/routes_gallery.py` — persist archive on mutate

`/api/album/archive` and `/api/album/unarchive` additionally call
`session.archive.add(fbid)` / `session.archive.remove(fbid)` so the change survives reload.
The in-memory `inventory.archived_albums` move stays exactly as today; persistence is
layered on top.

### 8. Frontend (`frontend/src/`)

- **`lib/api.js`** — add `listWorkspaces()`, `openWorkspace(id)`, `removeWorkspace(id, deleteFiles)`.
- **`routes/+page.svelte` (landing)** — two zones:
  1. **Workspace list** (new `lib/components/WorkspaceList.svelte`): cards sorted
     most-recently-opened first, each showing `display_name`, raw folder name (tooltip /
     muted subline), and last-opened. Click opens (`openWorkspace` → `goto('/gallery')`).
     Each card has a remove affordance → **double confirmation** dialog whose **second**
     step shows the exact path(s) to be deleted (managed) or states files are left on disk
     (external).
  2. **Add a workspace**: the existing drop-zip / folder-picker / typed-path UI, unchanged
     except it now registers + opens.
  - **Auto-resume**: on mount, `listWorkspaces()`; if `last_active` is set and the route
    was **not** reached with `?switch=1`, `openWorkspace(last_active)` then
    `goto('/gallery')`. With `?switch=1`, render the list (no auto-resume).
- **`routes/gallery/+page.svelte`** — add a **"Switch workspace"** toolbar control →
  `goto('/?switch=1')`. Show the active workspace's `display_name` in the header. If the
  gallery loads and `/api/session` reports no active session (e.g. after a backend
  restart), redirect to `/` (which auto-resumes).

### 9. Legacy migration (`_maybe_adopt_legacy_state`)

One-time: when a workspace's `state_dir` does not yet exist **and** a top-level marker
(`workspace/.migrated`) is absent, move the legacy flat files into the first-opened
workspace's state dir:

- `workspace/selection.json` → `state/<id>/selection.json`
- `workspace/renames.json`   → `state/<id>/renames.json`

Then write `workspace/.migrated` so it never runs again. Archive was never persisted, so
nothing to migrate. Move (not copy) so the legacy files don't linger as a false source of
truth. Guarded so it only adopts into the very first workspace after upgrade.

## Data flow

```
Landing mount
  GET /api/workspaces  ──► {workspaces[], last_active}
  if last_active and !?switch:  POST /api/workspaces/open {last_active} ──► gallery

Ingest zip
  zip stem ──► workspace/imports/<stem>/ registered?  ── yes ─► open existing (dedup)
                                                        └ no ──► extract ─► find_export_root
                                                                 ─► register(managed=True)
Open / ingest ──► _start_session(root, managed)
  build_inventory
  apply renames (state/<id>/renames.json)
  apply archive (state/<id>/archive.json)  ──► inventory.archived_albums
  Session{ selection, renames, archive, thumbs } all under state/<id>/
  registry.touch(id)  ──► last_active = id

Album archive/unarchive  ──► move in inventory + ArchiveState.add/remove (persisted)
Remove workspace ──► registry.remove(id) [+ rmtree imports/<id> + state/<id>, verified]
```

## Testing (TDD)

Backend (`pytest`, synthetic fixture only):

- `tests/test_naming.py` — `display_name` for both example names (drops suffix +
  `_annotation`), CamelCase split, and the no-date fallback (returns raw).
- `tests/test_registry.py` — register is idempotent on id; `list` sorted by
  `last_opened_ts` desc; `touch` updates `last_active`; `remove` drops the entry; caller
  supplies timestamps (no wall-clock in the module).
- `tests/test_archive_state.py` — `add`/`remove`/`is_archived` round-trip through
  `archive.json`.
- `tests/test_routes_workspaces.py` (TestClient) — `GET /api/workspaces` shape;
  `open` builds a session and returns inventory; `open` on a missing root errors; `remove`
  with `delete_files` removes a managed dir and verifies it's gone; `remove` on an external
  workspace leaves files.
- `tests/test_routes_ingest.py` — dedup: ingesting the same zip stem twice registers **one**
  workspace and the second call opens (no re-extract); per-workspace state files land under
  `state/<id>/`; two different exports keep separate `selection.json`.
- `tests/test_routes_gallery.py` — archiving an album writes `archive.json`; reopening the
  workspace restores it into `inventory.archived_albums`.
- Migration — first `open` with legacy flat files present moves them into `state/<id>/` and
  writes `.migrated`; a second workspace does not re-trigger it.

Frontend (`vitest`):

- `WorkspaceList` renders the list (display name + raw-name tooltip), calls `openWorkspace`
  on click, and requires the **two-step** confirm before calling `removeWorkspace`.

## Risks / edge cases

- **Windows file locks on delete.** Deleting a ~875 MB unzipped tree can hit
  `PermissionError` / `WinError 32` (Defender / open handles). The remove route must
  **verify** the directory is actually gone, retry a bounded number of times, and surface a
  clear error (registry entry retained) rather than silently reporting success. (Project is
  on `E:\`, not OneDrive, but locks still occur.)
- **Stale registry entry.** If an export folder is moved/deleted outside the app, `open`
  detects the missing root and the UI offers to remove the entry.
- **Zip stem ≠ inner export-root name.** Dedup pre-check keys off the zip stem for the
  fast path; the canonical id is always `export_root.name` after `find_export_root`, so a
  post-extract collision (same id already registered) also short-circuits to open-existing.
- **Auto-resume ↔ empty-session loop.** Gallery-with-no-session redirects to `/`
  (no `?switch`), which auto-resumes; `?switch=1` is the only state that shows the list, so
  no redirect loop.
- **Concurrency.** Single local user, one active session at a time — the registry file is
  read/written per request without locking, which is sufficient here.
