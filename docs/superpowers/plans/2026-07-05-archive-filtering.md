# Archive Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uncap the `Mobile uploads` & `Photos` albums and auto-move their UPPERCASE news-caption photos into a read-only **Archive** section that is excluded from the built `ready/` folder.

**Architecture:** A new pure module `inventory/archive.py` holds the album-name and caption-tag rules and a `partition_archive()` step the parser runs after building the inventory — so the UI and the build (which both call `build_inventory`) see one identical archived set. The selection policy gains a per-album uncapped set; the serializer exposes a nullable per-album cap plus an `archive` list; the builder subtracts archived fbids and drops posts left with no media. The SvelteKit UI adds an Archive nav entry and a read-only grid, and treats a `null` album cap as "no limit".

**Tech Stack:** Python 3.13 (FastAPI, Pydantic v2, pytest) via `uv`; SvelteKit (Svelte 5 runes, Skeleton v3 / Tailwind v4) with Vitest.

## Global Constraints

- Run backend tests with `UV_LINK_MODE=copy uv run --no-sync pytest -q` (src is on pythonpath; no reinstall needed).
- Lint with `uv run ruff check .` — line length 100, but E501 is not enforced.
- Frontend tests: from `frontend/`, `npm run test` (Vitest).
- **Never glob `posts/media/`** (~875 MB) — drive off JSON, verify specific files.
- Decode human text with `fix_mojibake` (already applied in the parser); this feature adds no new text source — a photo's `caption` is the post body, already resolved.
- UI is **light-only** — do not introduce dark-mode styling.
- Match rule is **case-sensitive UPPERCASE prefix, whole-word** (locked in the spec).
- Archived photos are **excluded from the build** (set-aside), and Archive is **read-only** (no selecting, no un-archive).
- Special albums matched by **normalized name** `strip().casefold() ∈ {"mobile uploads", "photos"}`.
- Spec: `docs/superpowers/specs/2026-07-05-archive-filtering-design.md`.

---

## File Structure

**Backend (create):**
- `src/streamlinify/inventory/archive.py` — album/caption classification rules + `partition_archive`.
- `tests/inventory/test_archive.py` — unit tests for the matchers.

**Backend (modify):**
- `src/streamlinify/inventory/models.py` — new fields on `Photo`, `Album`, `ExportInventory`.
- `src/streamlinify/inventory/parser.py` — call `partition_archive` before returning.
- `src/streamlinify/selection/policy.py` — `uncapped_albums` on `DefaultPolicy`.
- `src/streamlinify/web/routes_ingest.py` — derive uncapped set into the policy.
- `src/streamlinify/web/serializers.py` — per-album cap + `archive` list.
- `src/streamlinify/transform/builder.py` — subtract archived + drop empty posts.
- `tests/conftest.py` — new `archive_export_root` fixture.
- `tests/inventory/test_models.py`, `tests/inventory/test_parser.py`, `tests/selection/test_policy.py`, `tests/web/test_serializers.py`, `tests/web/test_gallery_routes.py`, `tests/transform/test_builder.py` — extend.

**Frontend (modify):**
- `frontend/src/lib/components/PhotoTile.svelte` — archive-tag badge (already has `selectable`).
- `frontend/src/lib/components/PhotoGrid.svelte` — thread `selectable`.
- `frontend/src/lib/components/PhotoPreview.svelte` — gate Keep button on `selectable`.
- `frontend/src/lib/components/AlbumList.svelte` — Archive nav row + per-album cap badge.
- `frontend/src/routes/gallery/+page.svelte` — archive view + uncapped-album handling.
- `frontend/src/lib/components/PhotoTile.test.js` — extend.

**Note (refines spec §5.1):** the archived-fbid subtraction lives in `build_ready_folder` (not the build route) so it is caller-independent and unit-testable, since the builder already calls `build_inventory` and thus knows the archived set.

---

### Task 1: Caption/album classification rules

**Files:**
- Create: `src/streamlinify/inventory/archive.py`
- Test: `tests/inventory/test_archive.py`

**Interfaces:**
- Produces: `SPECIAL_ALBUM_NAMES: frozenset[str]`, `ARCHIVE_KEYWORDS: tuple[str, ...]`, `is_special_album(name: str | None) -> bool`, `archive_tag(caption: str | None) -> str | None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/inventory/test_archive.py`:

```python
from streamlinify.inventory.archive import archive_tag, is_special_album


def test_is_special_album_normalizes_name():
    assert is_special_album("Mobile uploads") is True
    assert is_special_album("  PHOTOS  ") is True
    assert is_special_album("Photos") is True
    assert is_special_album("Animo Fest") is False
    assert is_special_album(None) is False


def test_archive_tag_matches_uppercase_prefix():
    assert archive_tag("BREAKING: Fire on campus") == "BREAKING"
    assert archive_tag("🚨 LOOK: Long lines today") == "LOOK"
    assert archive_tag("HAPPENING NOW: Gates open") == "HAPPENING NOW"
    assert archive_tag("JUST IN: Results are out") == "JUST IN"
    assert archive_tag("REST IN PEACE.") == "REST IN PEACE"
    assert archive_tag("COURTESY: Photo desk") == "COURTESY"
    assert archive_tag("WATCH: highlights") == "WATCH"
    assert archive_tag("UPDATE: schedule changed") == "UPDATE"


def test_archive_tag_rejects_non_tags():
    assert archive_tag("Look at this cute dog") is None
    assert archive_tag("We were watching the game") is None
    assert archive_tag("Updated our schedule") is None   # UPDATED != UPDATE (whole-word)
    assert archive_tag("LOOKING for volunteers") is None  # LOOKING != LOOK
    assert archive_tag("breaking: lowercase") is None      # case-sensitive
    assert archive_tag(None) is None
    assert archive_tag("") is None
    assert archive_tag("   ") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/inventory/test_archive.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'streamlinify.inventory.archive'`.

- [ ] **Step 3: Create the module**

Create `src/streamlinify/inventory/archive.py`:

```python
from __future__ import annotations

import re

# Albums the publication uses as photo dumps rather than themed sets. Matched by
# normalized name (strip + casefold) because an album's fb id is not knowable ahead
# of time. Update this set if Facebook renames these albums in a future export.
SPECIAL_ALBUM_NAMES = frozenset({"mobile uploads", "photos"})

# News-post caption tags. Ordered longest-phrase-first so a multi-word tag is tested
# before any shorter tag it could share a prefix with (defensive; no overlap today).
ARCHIVE_KEYWORDS: tuple[str, ...] = (
    "HAPPENING NOW",
    "REST IN PEACE",
    "JUST IN",
    "BREAKING",
    "COURTESY",
    "UPDATE",
    "WATCH",
    "LOOK",
)

# Leading emoji / whitespace / punctuation before the tag (e.g. "🚨 LOOK: ...").
_LEADING_NOISE = re.compile(r"^[^A-Za-z]+")


def is_special_album(name: str | None) -> bool:
    return (name or "").strip().casefold() in SPECIAL_ALBUM_NAMES


def archive_tag(caption: str | None) -> str | None:
    """Return the news tag a caption leads with, or None.

    Case-sensitive (tags are UPPERCASE by convention) and whole-word: the keyword
    must sit at the start (after leading emoji/space/punct) and be followed by a
    non-letter or end-of-string — so LOOKING / UPDATED / "Look at" never match.
    """
    if not caption:
        return None
    head = _LEADING_NOISE.sub("", caption)
    for kw in ARCHIVE_KEYWORDS:
        if head.startswith(kw):
            rest = head[len(kw):]
            if not rest or not rest[0].isalpha():
                return kw
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/inventory/test_archive.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/streamlinify/inventory/archive.py tests/inventory/test_archive.py
git commit -m "feat(inventory): archive keyword + special-album matchers"
```

---

### Task 2: Inventory model fields

**Files:**
- Modify: `src/streamlinify/inventory/models.py`
- Test: `tests/inventory/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Photo.archived: bool`, `Photo.archive_tag: str | None`; `Album.uncapped: bool`; `ExportInventory.archived_photos: list[Photo]`; `all_photos()` now includes archived photos.

- [ ] **Step 1: Write the failing test**

Append to `tests/inventory/test_models.py`:

```python
def test_all_photos_includes_archived():
    archived = _photo("z1", album_fbid="555")
    inv = ExportInventory(
        albums=[Album(fb_album_id="111", name="A", photos=[_photo("p1", "111")])],
        non_album_photos=[_photo("p2")],
        archived_photos=[archived],
    )
    assert {p.fbid for p in inv.all_photos()} == {"p1", "p2", "z1"}
    assert inv.photo_by_fbid("z1").fbid == "z1"


def test_photo_archive_defaults():
    p = _photo("p1", album_fbid="111")
    assert p.archived is False
    assert p.archive_tag is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/inventory/test_models.py -q`
Expected: FAIL — `ExportInventory` has no field `archived_photos` (Pydantic rejects the kwarg / `AttributeError`).

- [ ] **Step 3: Add the fields**

In `src/streamlinify/inventory/models.py`, add two fields to `Photo` (after `exists`):

```python
    exists: bool = True  # False when the referenced file is missing on disk (orphan)
    archived: bool = False  # True when set aside by a news-caption tag
    archive_tag: str | None = None  # the matched keyword, e.g. "BREAKING"
```

Add `uncapped` to `Album`:

```python
class Album(BaseModel):
    fb_album_id: str
    name: str
    photos: list[Photo] = []
    uncapped: bool = False  # True for the special dump albums (no per-album cap)
```

Add `archived_photos` to `ExportInventory` and include it in `all_photos`:

```python
class ExportInventory(BaseModel):
    albums: list[Album] = []
    non_album_photos: list[Photo] = []
    archived_photos: list[Photo] = []

    def all_photos(self) -> list[Photo]:
        out: list[Photo] = [p for a in self.albums for p in a.photos]
        out.extend(self.non_album_photos)
        out.extend(self.archived_photos)
        return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/inventory/test_models.py -q`
Expected: PASS (all tests in file, including the two new ones).

- [ ] **Step 5: Commit**

```bash
git add src/streamlinify/inventory/models.py tests/inventory/test_models.py
git commit -m "feat(inventory): archived/uncapped fields on models"
```

---

### Task 3: Partition archive during parsing (+ fixture)

**Files:**
- Modify: `src/streamlinify/inventory/archive.py` (add `partition_archive`)
- Modify: `src/streamlinify/inventory/parser.py`
- Modify: `tests/conftest.py` (new `archive_export_root` fixture)
- Test: `tests/inventory/test_parser.py`

**Interfaces:**
- Consumes: `is_special_album`, `archive_tag` (Task 1); model fields (Task 2).
- Produces: `partition_archive(inventory: ExportInventory) -> None` (mutates in place); pytest fixture `archive_export_root` returning a `Path` with albums `Mobile uploads` (fbid `555`), `Photos` (fbid `666`), `Animo Fest` (fbid `111`).

- [ ] **Step 1: Add the `archive_export_root` fixture**

Append to `tests/conftest.py` (reuses existing `_img` and `_photo_record` helpers):

```python
@pytest.fixture
def archive_export_root(tmp_path: Path) -> Path:
    """Export with the two special albums plus a normal one, and posts that supply
    matching + non-matching captions. Used only by archive-feature tests."""
    root = tmp_path / "archive_export"
    media = root / "posts" / "media"
    album_dir = root / "posts" / "album"
    album_dir.mkdir(parents=True)

    # Special album "Mobile uploads" (dir Mobileuploads_555): u01 tagged, u02 not, u03 no post
    u_photos = [_photo_record("Mobileuploads_555", f"u0{n}", f"U{n}") for n in (1, 2, 3)]
    (album_dir / "0.json").write_text(
        json.dumps({"name": "Mobile uploads", "photos": u_photos}), encoding="utf-8"
    )
    for n in (1, 2, 3):
        _img(media / "Mobileuploads_555" / f"u0{n}.jpg")

    # Special album "Photos" (dir Photos_666): p01 tagged, p02 no post
    p_photos = [_photo_record("Photos_666", f"p0{n}", f"P{n}") for n in (1, 2)]
    (album_dir / "1.json").write_text(
        json.dumps({"name": "Photos", "photos": p_photos}), encoding="utf-8"
    )
    for n in (1, 2):
        _img(media / "Photos_666" / f"p0{n}.jpg")

    # Normal capped album "Animo Fest" (dir AnimoFest_111): a01 has a tag caption but
    # this album is NOT special, so the photo must stay put.
    (album_dir / "2.json").write_text(
        json.dumps({"name": "Animo Fest", "photos": [_photo_record("AnimoFest_111", "a01", "A1")]}),
        encoding="utf-8",
    )
    _img(media / "AnimoFest_111" / "a01.jpg")

    posts = [
        {"data": [{"post": "BREAKING: Fire on campus"}],
         "attachments": [{"data": [{"media": _photo_record("Mobileuploads_555", "u01", "U1")}]}]},
        {"data": [{"post": "Look at these cute dogs"}],
         "attachments": [{"data": [{"media": _photo_record("Mobileuploads_555", "u02", "U2")}]}]},
        {"data": [{"post": "LOOK: Long lines today"}],
         "attachments": [{"data": [{"media": _photo_record("Photos_666", "p01", "P1")}]}]},
        {"data": [{"post": "UPDATE: schedule changed"}],
         "attachments": [{"data": [{"media": _photo_record("AnimoFest_111", "a01", "A1")}]}]},
    ]
    (root / "posts" / "profile_posts_1.json").write_text(json.dumps(posts), encoding="utf-8")

    for name in (
        "videos.json",
        "content_sharing_links_you_have_created.json",
        "edits_you_made_to_posts.json",
        "places_you_have_been_tagged_in.json",
    ):
        (root / "posts" / name).write_text("[]", encoding="utf-8")

    return root
```

- [ ] **Step 2: Write the failing parser test**

Append to `tests/inventory/test_parser.py`:

```python
def test_build_inventory_partitions_archive(archive_export_root: Path):
    inv = build_inventory(archive_export_root)
    by_id = {a.fb_album_id: a for a in inv.albums}

    # Special albums are uncapped and keep only their non-tagged photos.
    assert by_id["555"].uncapped is True
    assert by_id["666"].uncapped is True
    assert {p.fbid for p in by_id["555"].photos} == {"u02", "u03"}
    assert {p.fbid for p in by_id["666"].photos} == {"p02"}

    # Tagged photos moved to archived_photos, with their tag recorded.
    archived = {p.fbid: p for p in inv.archived_photos}
    assert set(archived) == {"u01", "p01"}
    assert archived["u01"].archived is True
    assert archived["u01"].archive_tag == "BREAKING"
    assert archived["p01"].archive_tag == "LOOK"

    # A tag caption in a NON-special album is left untouched (album stays capped).
    assert by_id["111"].uncapped is False
    assert {p.fbid for p in by_id["111"].photos} == {"a01"}
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/inventory/test_parser.py::test_build_inventory_partitions_archive -q`
Expected: FAIL — `AttributeError: 'Album' object has no attribute 'uncapped'` is already satisfied by Task 2, so instead it fails because `archived_photos` is empty and `by_id["555"].photos` still contains `u01` (partition not wired yet).

- [ ] **Step 4: Add `partition_archive` and call it from the parser**

Append to `src/streamlinify/inventory/archive.py`:

```python
from .models import ExportInventory, Photo  # noqa: E402  (kept next to its user)


def partition_archive(inventory: ExportInventory) -> None:
    """Move news-tagged photos out of the two special albums into `archived_photos`.

    Mutates in place: each special album is marked `uncapped` and keeps only its
    non-tagged photos; a tagged photo gets `archived=True` + its tag and moves to
    `inventory.archived_photos`. Non-special albums are untouched. Order preserved.
    """
    for album in inventory.albums:
        if not is_special_album(album.name):
            continue
        album.uncapped = True
        kept: list[Photo] = []
        for photo in album.photos:
            tag = archive_tag(photo.caption)
            if tag is None:
                kept.append(photo)
            else:
                photo.archived = True
                photo.archive_tag = tag
                inventory.archived_photos.append(photo)
        album.photos = kept
```

In `src/streamlinify/inventory/parser.py`, add the import and call it before returning. Change the import line:

```python
from .archive import partition_archive
from .models import Album, ExportInventory, Photo
```

And replace the final `return` of `build_inventory`:

```python
    inventory = ExportInventory(albums=albums, non_album_photos=non_album)
    partition_archive(inventory)
    return inventory
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/inventory/test_parser.py -q`
Expected: PASS (existing `test_build_inventory` unaffected — its albums are "Animo Fest"/"Café Night", neither special — plus the new test).

- [ ] **Step 6: Commit**

```bash
git add src/streamlinify/inventory/archive.py src/streamlinify/inventory/parser.py tests/conftest.py tests/inventory/test_parser.py
git commit -m "feat(inventory): partition news-caption photos into archive during parse"
```

---

### Task 4: Uncapped selection policy + ingest wiring

**Files:**
- Modify: `src/streamlinify/selection/policy.py`
- Modify: `src/streamlinify/web/routes_ingest.py:45-56`
- Test: `tests/selection/test_policy.py`, `tests/web/test_gallery_routes.py`

**Interfaces:**
- Consumes: `Album.uncapped` (Task 2); `archive_export_root` (Task 3).
- Produces: `DefaultPolicy(max_per_album=..., uncapped_albums=frozenset())`; `_start_session` builds `uncapped_albums` from `inventory.albums`.

- [ ] **Step 1: Write the failing policy test**

Append to `tests/selection/test_policy.py`:

```python
def test_uncapped_album_ignores_max():
    policy = DefaultPolicy(max_per_album=3, uncapped_albums=frozenset({"555"}))
    assert policy.can_select("555", 99) is True   # special album: never full
    assert policy.can_select("111", 3) is False    # normal album: still capped
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/selection/test_policy.py::test_uncapped_album_ignores_max -q`
Expected: FAIL — `TypeError: DefaultPolicy.__init__() got an unexpected keyword argument 'uncapped_albums'`.

- [ ] **Step 3: Add `uncapped_albums` to the policy**

In `src/streamlinify/selection/policy.py`, update `DefaultPolicy`:

```python
@dataclass
class DefaultPolicy:
    """Named-album cap; non-album photos are auto-kept and not pickable (Decision B).

    Albums in `uncapped_albums` (the "Mobile uploads" / "Photos" dumps) have no cap.
    To make non-album photos deselectable later, add a sibling policy whose
    `non_album_selectable()` returns True — no change to SelectionState needed.
    """

    max_per_album: int = settings.max_per_album
    uncapped_albums: frozenset[str] = frozenset()

    def can_select(self, album_fbid: str, current_count: int) -> bool:
        if album_fbid in self.uncapped_albums:
            return True
        return current_count < self.max_per_album

    def non_album_selectable(self) -> bool:
        return False
```

- [ ] **Step 4: Run the policy test to verify it passes**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/selection/test_policy.py -q`
Expected: PASS (all tests).

- [ ] **Step 5: Write the failing wiring test**

Append to `tests/web/test_gallery_routes.py` (imports `create_app` and `TestClient` are already at the top of that file — verify and add if missing):

```python
def test_inventory_marks_special_albums_uncapped(archive_export_root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(archive_export_root)})

    body = client.get("/api/inventory").json()
    caps = {a["name"]: a["max_per_album"] for a in body["albums"]}
    assert caps["Mobile uploads"] is None
    assert caps["Photos"] is None
    assert caps["Animo Fest"] == 10
    assert {p["fbid"] for p in body["archive"]} == {"u01", "p01"}
```

If `test_gallery_routes.py` lacks the imports, add at the top:

```python
from fastapi.testclient import TestClient

from streamlinify.app import create_app
```

- [ ] **Step 6: Run the wiring test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/web/test_gallery_routes.py::test_inventory_marks_special_albums_uncapped -q`
Expected: FAIL — `KeyError: 'max_per_album'` (album dict) / `KeyError: 'archive'` (payload). The serializer is not updated until Task 5, but the policy wiring must be done now; this test fully passes only after Task 5. **Expected FAIL here; it is re-run green in Task 5.**

- [ ] **Step 7: Wire the uncapped set into `_start_session`**

In `src/streamlinify/web/routes_ingest.py`, update `_start_session` to build the policy from the inventory:

```python
def _start_session(request: Request, export_root: Path) -> dict:
    report = validate_export(export_root)
    if not report.ok:
        return {"ok": False, "errors": list(report.missing)}
    workspace = settings.workspace_dir
    inventory = build_inventory(export_root)
    uncapped = frozenset(a.fb_album_id for a in inventory.albums if a.uncapped)
    request.app.state.session = Session(
        export_root=export_root,
        inventory=inventory,
        selection=SelectionState(
            workspace / "selection.json", DefaultPolicy(uncapped_albums=uncapped)
        ),
        thumbnails=ThumbnailService(workspace / "thumbs"),
    )
    return {"ok": True, "errors": [], "export_name": export_root.name}
```

- [ ] **Step 8: Commit (wiring in place; serializer follows)**

```bash
git add src/streamlinify/selection/policy.py src/streamlinify/web/routes_ingest.py tests/selection/test_policy.py tests/web/test_gallery_routes.py
git commit -m "feat(selection): uncapped albums in policy + ingest wiring"
```

---

### Task 5: Serializer — per-album cap + archive list

**Files:**
- Modify: `src/streamlinify/web/serializers.py`
- Test: `tests/web/test_serializers.py`, `tests/web/test_gallery_routes.py` (re-run Task 4's test)

**Interfaces:**
- Consumes: `Album.uncapped`, `Photo.archive_tag`, `ExportInventory.archived_photos`.
- Produces: each album dict gains `"max_per_album": int | None`; payload gains `"archive": list[dict]` with keys `fbid, caption, archive_tag, exists`.

- [ ] **Step 1: Write the failing serializer test**

Append to `tests/web/test_serializers.py`:

```python
def test_payload_includes_archive_and_uncapped(tmp_path):
    inv = ExportInventory(
        albums=[
            Album(
                fb_album_id="555", name="Mobile uploads", uncapped=True,
                photos=[Photo(fbid="u02", original_uri="p/u02.jpg", resolved_path="x",
                              caption="Look at dogs", exists=True, album_fbid="555")],
            ),
            Album(
                fb_album_id="111", name="Animo Fest",
                photos=[Photo(fbid="a01", original_uri="p/a01.jpg", resolved_path="x",
                              caption=None, exists=True, album_fbid="111")],
            ),
        ],
        archived_photos=[
            Photo(fbid="u01", original_uri="p/u01.jpg", resolved_path="x",
                  caption="BREAKING: fire", exists=True, album_fbid="555",
                  archived=True, archive_tag="BREAKING"),
        ],
    )
    sel = SelectionState(tmp_path / "sel.json", DefaultPolicy())
    payload = inventory_payload("e", inv, sel, 10)

    caps = {a["name"]: a["max_per_album"] for a in payload["albums"]}
    assert caps["Mobile uploads"] is None      # uncapped
    assert caps["Animo Fest"] == 10            # capped
    assert payload["archive"] == [
        {"fbid": "u01", "caption": "BREAKING: fire", "archive_tag": "BREAKING", "exists": True}
    ]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/web/test_serializers.py::test_payload_includes_archive_and_uncapped -q`
Expected: FAIL — `KeyError: 'max_per_album'` on the album dict.

- [ ] **Step 3: Update the serializer**

Replace `src/streamlinify/web/serializers.py` body with:

```python
from __future__ import annotations

from ..inventory.models import ExportInventory, Photo
from ..selection.state import SelectionState


def _photo(p: Photo, selected: bool | None = None) -> dict:
    d: dict = {"fbid": p.fbid, "caption": p.caption, "exists": p.exists}
    if selected is not None:
        d["selected"] = selected
    return d


def _archive_photo(p: Photo) -> dict:
    return {
        "fbid": p.fbid,
        "caption": p.caption,
        "archive_tag": p.archive_tag,
        "exists": p.exists,
    }


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
            "max_per_album": None if a.uncapped else max_per_album,
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
        "archive": [_archive_photo(p) for p in inventory.archived_photos],
    }
```

- [ ] **Step 4: Run the serializer + wiring tests to verify they pass**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/web/test_serializers.py tests/web/test_gallery_routes.py -q`
Expected: PASS — including `test_inventory_marks_special_albums_uncapped` from Task 4 (now green) and the unchanged `test_payload_shape`.

- [ ] **Step 5: Commit**

```bash
git add src/streamlinify/web/serializers.py tests/web/test_serializers.py
git commit -m "feat(web): serialize per-album cap + archive list"
```

---

### Task 6: Builder — exclude archived + drop empty posts

**Files:**
- Modify: `src/streamlinify/transform/builder.py:38-92`
- Test: `tests/transform/test_builder.py`

**Interfaces:**
- Consumes: `ExportInventory.archived_photos` (built internally via `build_inventory`); `archive_export_root` fixture.
- Produces: `build_ready_folder` now subtracts archived fbids from `keep_fbids` and omits posts left with no attachments.

- [ ] **Step 1: Write the failing test**

Append to `tests/transform/test_builder.py`:

```python
def test_build_excludes_archived_and_drops_empty_posts(archive_export_root: Path, tmp_path: Path):
    dest = tmp_path / "ready"
    # A stale keep set that even names the archived photos u01 / p01.
    keep = {"u01", "u02", "u03", "p01", "p02", "a01"}
    build_ready_folder(archive_export_root, dest, keep)

    # Archived photos are never copied, even though present + in keep.
    assert not (dest / "posts" / "media" / "Mobileuploads_555" / "u01.jpg").exists()
    assert not (dest / "posts" / "media" / "Photos_666" / "p01.jpg").exists()
    # Non-archived kept photos are copied.
    assert (dest / "posts" / "media" / "Mobileuploads_555" / "u02.jpg").exists()

    posts = json.loads((dest / "posts" / "profile_posts_1.json").read_text(encoding="utf-8"))
    bodies = [d["post"] for post in posts for d in post.get("data", []) if "post" in d]
    # Posts whose only media was archived are dropped entirely.
    assert "BREAKING: Fire on campus" not in bodies
    assert "LOOK: Long lines today" not in bodies
    # Posts with surviving media remain.
    assert "Look at these cute dogs" in bodies   # u02 kept
    assert "UPDATE: schedule changed" in bodies  # a01 kept (non-special album)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/transform/test_builder.py::test_build_excludes_archived_and_drops_empty_posts -q`
Expected: FAIL — `u01.jpg` IS copied (archived not yet subtracted) and the `BREAKING` post survives (empty posts not yet dropped).

- [ ] **Step 3: Update the builder**

In `src/streamlinify/transform/builder.py`, at the top of `build_ready_folder`, subtract archived fbids right after building the inventory:

```python
def build_ready_folder(export_root: Path, dest: Path, keep_fbids: set[str]) -> BuildResult:
    inventory = build_inventory(export_root)
    # Archived (news-caption) photos are set aside — never carried into the build,
    # even if a stale selection.json still names one.
    keep_fbids = keep_fbids - {p.fbid for p in inventory.archived_photos}
    dest.mkdir(parents=True, exist_ok=True)
```

Then, in the profile_posts filtering block, drop posts that end up with no attachments. Change the loop's tail so that after rebuilding each post's `attachments`, empty posts are removed before writing:

```python
    posts_path = export_root / "posts" / "profile_posts_1.json"
    if posts_path.exists():
        posts = json.loads(posts_path.read_text(encoding="utf-8"))
        for post in posts:
            for att in post.get("attachments", []):
                att["data"] = [
                    d
                    for d in att.get("data", [])
                    if "media" in d and photo_fbid(d["media"]["uri"]) in present_fbids
                ]
            post["attachments"] = [att for att in post.get("attachments", []) if att["data"]]
        # A post with no surviving media (all archived / non-selected / orphaned) is
        # dead metadata for the photo archive — drop it so the ready posts mirror the
        # media that is actually present.
        posts = [post for post in posts if post.get("attachments")]
        (dest / "posts").mkdir(parents=True, exist_ok=True)
        (dest / "posts" / "profile_posts_1.json").write_text(
            json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8"
        )
```

- [ ] **Step 4: Run the builder tests to verify they pass**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/transform/test_builder.py -q`
Expected: PASS — the new test plus the existing `test_build_filtered_mirror` / `test_idempotent_rerun` (their posts all retain surviving media, so none are dropped).

- [ ] **Step 5: Run the full backend suite**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest -q`
Expected: PASS (all backend tests, including `tests/web/test_build_route.py` — its posts keep `a01` / `m01`, so no empty-post drop changes its assertions).

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check .
git add src/streamlinify/transform/builder.py tests/transform/test_builder.py
git commit -m "feat(transform): exclude archived photos and drop media-less posts"
```

---

### Task 7: Read-only tiles — badge + preview gating

**Files:**
- Modify: `frontend/src/lib/components/PhotoTile.svelte`
- Modify: `frontend/src/lib/components/PhotoGrid.svelte`
- Modify: `frontend/src/lib/components/PhotoPreview.svelte`
- Test: `frontend/src/lib/components/PhotoTile.test.js`

**Interfaces:**
- Consumes: `photo.archive_tag` from the API.
- Produces: `PhotoTile` shows a tag badge and is inert when `selectable={false}`; `PhotoGrid` accepts and forwards `selectable`; `PhotoPreview` accepts `selectable` and hides the Keep button when false.

- [ ] **Step 1: Write the failing PhotoTile test**

Append a test inside the `describe('PhotoTile', ...)` block in `frontend/src/lib/components/PhotoTile.test.js`:

```javascript
	it('is inert and shows its tag when not selectable (archive tile)', async () => {
		const onToggle = vi.fn();
		render(PhotoTile, {
			props: {
				photo: { fbid: 'u01', exists: true, caption: 'BREAKING: fire', archive_tag: 'BREAKING' },
				src: '/x.jpg',
				selectable: false,
				onToggle
			}
		});
		const tile = screen.getByTestId('tile-u01');
		expect(tile).toBeDisabled();
		await fireEvent.click(tile);
		expect(onToggle).not.toHaveBeenCalled();
		expect(screen.getByText('BREAKING')).toBeInTheDocument();
	});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm run test -- --run PhotoTile`
Expected: FAIL — no element with text `BREAKING` (badge not rendered yet).

- [ ] **Step 3: Add the tag badge to PhotoTile**

In `frontend/src/lib/components/PhotoTile.svelte`, inside the `{#if photo.exists}` block, immediately after the opening `<img ... />` tag (before the selected/affordance badges), add:

```svelte
		{#if photo.archive_tag}
			<span
				class="pointer-events-none absolute left-2 top-2 rounded bg-surface-900/75 px-1.5 py-0.5 text-[0.6rem] font-semibold uppercase tracking-wide text-surface-50"
			>
				{photo.archive_tag}
			</span>
		{/if}
```

(No other change needed: `interactive = selectable && photo.exists && !blocked` already makes the button `disabled` and the `onclick` a no-op when `selectable` is false.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm run test -- --run PhotoTile`
Expected: PASS (all PhotoTile tests).

- [ ] **Step 5: Thread `selectable` through PhotoGrid**

In `frontend/src/lib/components/PhotoGrid.svelte`, add `selectable` to the props and pass it down:

```svelte
	let { album, thumb, full = false, size = 'm', selectable = true, onToggle, onContextMenu } = $props();
```

and update the tile usage:

```svelte
			<PhotoTile {photo} src={photo.exists ? thumb(photo.fbid) : ''} {full} {selectable} {onToggle} />
```

- [ ] **Step 6: Gate the Keep button in PhotoPreview**

In `frontend/src/lib/components/PhotoPreview.svelte`, add `selectable` to the props:

```svelte
	let {
		album,
		thumb,
		preview,
		startIndex = 0,
		full = false,
		selectable = true,
		onToggle,
		onClose
	} = $props();
```

and change the Keep-button guard from `{#if current?.exists}` to:

```svelte
				{#if selectable && current?.exists}
```

- [ ] **Step 7: Run the frontend suite**

Run: `cd frontend && npm run test -- --run`
Expected: PASS (existing tests unchanged; PhotoTile’s new test green).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/components/PhotoTile.svelte frontend/src/lib/components/PhotoGrid.svelte frontend/src/lib/components/PhotoPreview.svelte frontend/src/lib/components/PhotoTile.test.js
git commit -m "feat(ui): archive tag badge + read-only tile/preview support"
```

---

### Task 8: AlbumList — Archive nav + per-album cap badge

**Files:**
- Modify: `frontend/src/lib/components/AlbumList.svelte`
- Test: `frontend/src/lib/components/AlbumList.test.js` (create)

**Interfaces:**
- Consumes: `album.max_per_album` (nullable) and `archiveCount` from the page.
- Produces: `AlbumList` props `{ albums, nonAlbumCount, archiveCount, activeId, onSelect, onContextMenu }`; selecting Archive calls `onSelect('__archive__')`. Per-album badge shows `count` only (no denominator) when `max_per_album` is null.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/components/AlbumList.test.js`:

```javascript
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import AlbumList from './AlbumList.svelte';

const albums = [
	{ fb_album_id: '111', name: 'Animo Fest', count_selected: 2, max_per_album: 10 },
	{ fb_album_id: '555', name: 'Mobile uploads', count_selected: 3, max_per_album: null }
];

describe('AlbumList', () => {
	it('shows a denominator only for capped albums', () => {
		render(AlbumList, { props: { albums, nonAlbumCount: 0, archiveCount: 2, activeId: '111', onSelect: vi.fn() } });
		expect(screen.getByText('2/10')).toBeInTheDocument();     // capped
		expect(screen.queryByText('3/10')).not.toBeInTheDocument(); // uncapped: no denominator
	});

	it('selects the archive section', async () => {
		const onSelect = vi.fn();
		render(AlbumList, { props: { albums, nonAlbumCount: 0, archiveCount: 2, activeId: '111', onSelect } });
		await fireEvent.click(screen.getByText('Archive'));
		expect(onSelect).toHaveBeenCalledWith('__archive__');
	});
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm run test -- --run AlbumList`
Expected: FAIL — the component still reads a global `maxPerAlbum`, renders `3/10`, and has no `Archive` control.

- [ ] **Step 3: Rewrite AlbumList**

Replace `frontend/src/lib/components/AlbumList.svelte` with:

```svelte
<script>
	let { albums, nonAlbumCount, archiveCount = 0, activeId, onSelect, onContextMenu } = $props();
</script>

<nav aria-label="Albums" class="flex flex-col gap-1">
	<p class="px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-surface-500">
		Albums <span class="font-normal text-surface-400">· {albums.length}</span>
	</p>

	{#each albums as a (a.fb_album_id)}
		{@const capped = a.max_per_album != null}
		{@const full = capped && a.count_selected >= a.max_per_album}
		{@const active = a.fb_album_id === activeId}
		<button
			type="button"
			class="flex items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
			class:bg-primary-100={active}
			class:text-primary-900={active}
			class:font-semibold={active}
			class:text-surface-700={!active}
			class:hover:bg-surface-200={!active}
			onclick={() => onSelect(a.fb_album_id)}
			oncontextmenu={(e) => {
				e.preventDefault();
				onContextMenu?.(a, e);
			}}
			aria-current={active ? 'true' : undefined}
		>
			<span class="truncate">{a.name}</span>
			<span
				class="ml-auto inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium tabular-nums"
				class:bg-warning-200={full}
				class:text-warning-900={full}
				class:bg-primary-200={!full && a.count_selected > 0}
				class:text-primary-900={!full && a.count_selected > 0}
				class:bg-surface-200={a.count_selected === 0}
				class:text-surface-600={a.count_selected === 0}
				title={capped
					? full
						? 'Album is full'
						: `${a.count_selected} of ${a.max_per_album} selected`
					: `${a.count_selected} selected · no limit`}
			>
				{#if full}
					<svg viewBox="0 0 24 24" class="size-3" fill="none" stroke="currentColor" stroke-width="2.5"
						stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>
				{/if}
				{#if capped}{a.count_selected}/{a.max_per_album}{:else}{a.count_selected}{/if}
			</span>
		</button>
	{/each}

	{#if archiveCount > 0}
		{@const active = activeId === '__archive__'}
		<div class="my-1 h-px bg-surface-300"></div>
		<button
			type="button"
			class="flex items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
			class:bg-primary-100={active}
			class:text-primary-900={active}
			class:font-semibold={active}
			class:text-surface-700={!active}
			class:hover:bg-surface-200={!active}
			onclick={() => onSelect('__archive__')}
			aria-current={active ? 'true' : undefined}
			title="News-caption photos set aside — excluded from the build."
		>
			<svg viewBox="0 0 24 24" class="size-4 shrink-0" fill="none" stroke="currentColor"
				stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="4" rx="1" /><path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8M10 12h4" /></svg>
			<span class="truncate">Archive</span>
			<span class="ml-auto shrink-0 rounded-full bg-surface-200 px-2 py-0.5 text-xs font-medium tabular-nums text-surface-600">{archiveCount}</span>
		</button>
	{/if}

	<div class="my-1 h-px bg-surface-300"></div>

	<div
		class="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-surface-500"
		title="All non-album photos are kept automatically and can't be deselected."
	>
		<svg viewBox="0 0 24 24" class="size-4 shrink-0 text-surface-400" fill="none" stroke="currentColor"
			stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5" /></svg>
		<span>Auto-kept</span>
		<span class="ml-auto shrink-0 tabular-nums text-surface-400">{nonAlbumCount}</span>
	</div>
</nav>
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm run test -- --run AlbumList`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/components/AlbumList.svelte frontend/src/lib/components/AlbumList.test.js
git commit -m "feat(ui): Archive nav entry + per-album cap badge in AlbumList"
```

---

### Task 9: Gallery page — Archive view + uncapped albums

**Files:**
- Modify: `frontend/src/routes/gallery/+page.svelte`

**Interfaces:**
- Consumes: `inventory.archive` (array), each album's `max_per_album` (nullable), `AlbumList` `archiveCount` prop, `PhotoGrid`/`PhotoPreview` `selectable` prop.
- Produces: no exported interface (page glue). Verified by running the app.

This task is UI integration glue with no unit harness; verify by building and driving the app (Step 6).

- [ ] **Step 1: Add archive state and per-album cap derivations**

In `frontend/src/routes/gallery/+page.svelte`, in the `<script>`, add archive state after the `inventory` line and replace the cap derivations. After:

```javascript
	let inventory = $state(data.inventory);
	let activeId = $state(inventory.albums[0]?.fb_album_id ?? null);
```

add:

```javascript
	let archive = $derived(inventory.archive ?? []);
	let showArchive = $derived(activeId === '__archive__');
```

Then replace these two lines:

```javascript
	let activeAlbum = $derived(inventory.albums.find((a) => a.fb_album_id === activeId) ?? null);
	let activeFull = $derived(
		activeAlbum ? activeAlbum.count_selected >= inventory.max_per_album : false
	);
```

with cap-aware versions:

```javascript
	let activeAlbum = $derived(inventory.albums.find((a) => a.fb_album_id === activeId) ?? null);
	let activeCap = $derived(activeAlbum ? activeAlbum.max_per_album : null); // null = no limit
	let activeFull = $derived(
		activeAlbum && activeCap != null ? activeAlbum.count_selected >= activeCap : false
	);
```

- [ ] **Step 2: Add an archive right-click menu and preview handler**

Still in the `<script>`, add a context-menu handler for archive tiles (mirrors `openPhotoMenu` but points at the `archive` list and offers no toggle):

```javascript
	// Right-click an archived photo → preview it (read-only) or open its file.
	function openArchiveMenu(photo, e) {
		const index = archive.findIndex((p) => p.fbid === photo.fbid);
		menu = {
			open: true,
			x: e.clientX,
			y: e.clientY,
			items: [
				{ label: 'Preview', icon: 'preview', onSelect: () => openPreviewAt(index) },
				{
					label: 'Show in File Explorer',
					icon: 'folder',
					disabled: !photo.exists,
					hint: photo.exists ? undefined : 'missing',
					onSelect: () => revealOnDisk({ photoFbid: photo.fbid })
				}
			]
		};
	}
```

- [ ] **Step 3: Pass `archiveCount` to AlbumList**

In the template, update the `<AlbumList ... />` usage: remove the `maxPerAlbum` prop (albums now carry their own cap) and add `archiveCount`:

```svelte
			<AlbumList
				albums={inventory.albums}
				nonAlbumCount={inventory.non_album.length}
				archiveCount={archive.length}
				{activeId}
				onSelect={(id) => (activeId = id)}
				onContextMenu={openAlbumMenu}
			/>
```

- [ ] **Step 4: Render the Archive pane and make the album header cap-aware**

Replace the right-pane `<section class="min-w-0"> … </section>` block so it renders the Archive view when active, and uses `activeCap` instead of `inventory.max_per_album`:

```svelte
	<!-- Right pane: active album OR the read-only archive -->
	<section class="min-w-0">
		{#if showArchive}
			<header
				class="sticky top-[5.25rem] z-20 mb-4 bg-surface-100 pt-1 pb-3 before:pointer-events-none before:absolute before:inset-x-0 before:bottom-full before:h-24 before:bg-surface-100 before:content-['']"
			>
				<div class="flex min-w-0 items-baseline gap-3">
					<h1 class="truncate text-xl font-semibold tracking-tight text-surface-900">Archive</h1>
					<p class="shrink-0 text-sm font-medium tabular-nums text-surface-500">{archive.length} set aside</p>
				</div>
				<p class="mt-2 text-sm text-surface-500">
					Photos posted with a news caption (BREAKING, LOOK, …) from Mobile uploads &amp; Photos.
					These are excluded from the build. Right-click to preview or open the file.
				</p>
			</header>

			{#if archive.length}
				<PhotoGrid
					album={{ name: 'Archive', photos: archive }}
					thumb={thumbUrl}
					size={gridSize}
					selectable={false}
					onContextMenu={openArchiveMenu}
				/>
			{/if}
		{:else if activeAlbum}
			<header
				class="sticky top-[5.25rem] z-20 mb-4 bg-surface-100 pt-1 pb-3 before:pointer-events-none before:absolute before:inset-x-0 before:bottom-full before:h-24 before:bg-surface-100 before:content-['']"
			>
				<div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
					<div class="flex min-w-0 items-baseline gap-3">
						<h1 class="truncate text-xl font-semibold tracking-tight text-surface-900">
							{activeAlbum.name}
						</h1>
						<p
							class="shrink-0 text-sm font-medium tabular-nums"
							class:text-warning-700={activeFull}
							class:text-surface-500={!activeFull}
						>
							{#if activeCap != null}
								{activeAlbum.count_selected} / {activeCap} selected
							{:else}
								{activeAlbum.count_selected} selected · no limit
							{/if}
						</p>
					</div>
					<ViewControls
						size={gridSize}
						onSize={setSize}
						onOpenPreview={() => openPreviewAt(0)}
						previewDisabled={activeAlbum.photos.length === 0}
					/>
				</div>
				{#if activeCap != null}
					<div class="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-200">
						<div
							class="h-full rounded-full transition-[width] duration-300"
							class:bg-warning-500={activeFull}
							class:bg-primary-600={!activeFull}
							style="width: {(activeAlbum.count_selected / activeCap) * 100}%"
						></div>
					</div>
				{/if}
				<p class="mt-2 text-sm text-surface-500">
					{#if activeCap == null}
						Click photos to keep as many as you want from this album. Right-click a photo for more.
					{:else if activeFull}
						This album is full. Remove a photo to choose a different one.
					{:else}
						Click photos to keep up to {activeCap} from this album. Right-click a photo for more.
					{/if}
				</p>
			</header>

			<PhotoGrid
				album={activeAlbum}
				thumb={thumbUrl}
				full={activeFull}
				size={gridSize}
				{onToggle}
				onContextMenu={openPhotoMenu}
			/>
		{:else}
			<div
				class="grid place-items-center rounded-xl border border-dashed border-surface-300 bg-surface-50 px-6 py-16 text-center"
			>
				<p class="font-medium text-surface-700">No named albums in this export</p>
				<p class="mt-1 text-sm text-surface-500">
					All {inventory.non_album.length} photos are non-album and will be kept automatically.
				</p>
			</div>
		{/if}
	</section>
```

- [ ] **Step 5: Make the full-screen preview handle the archive list**

Replace the `{#if previewOpen && activeAlbum && activeAlbum.photos.length}` preview block with one that also serves the archive (read-only, no Keep button):

```svelte
{#if previewOpen && showArchive && archive.length}
	<PhotoPreview
		album={{ name: 'Archive', photos: archive }}
		thumb={thumbUrl}
		preview={previewUrl}
		selectable={false}
		startIndex={previewStart}
		onToggle={() => {}}
		onClose={() => (previewOpen = false)}
	/>
{:else if previewOpen && activeAlbum && activeAlbum.photos.length}
	<PhotoPreview
		album={activeAlbum}
		thumb={thumbUrl}
		preview={previewUrl}
		full={activeFull}
		startIndex={previewStart}
		{onToggle}
		onClose={() => (previewOpen = false)}
	/>
{/if}
```

- [ ] **Step 6: Verify by building and driving the app**

Backend (from repo root), then frontend build:

```bash
UV_LINK_MODE=copy uv run --no-sync pytest -q
cd frontend && npm run test -- --run && npm run build
```

Expected: backend + frontend tests PASS; `npm run build` completes with no Svelte errors.

Then run both servers and confirm in the browser (`http://localhost:5173`, API on `:8000`) against the real export in `workspace/import/unzipped/`:
- `Mobile uploads` and `Photos` show a plain count badge (no `/10`) and let you select more than 10.
- An **Archive** entry appears with a count; clicking it shows a read-only grid with tag badges; tiles don't toggle; right-click → Preview / Show in File Explorer works.
- Build, then inspect `workspace/ready/<export>/`: archived photos' files are absent, and `posts/profile_posts_1.json` contains no post whose only media was archived.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/routes/gallery/+page.svelte
git commit -m "feat(ui): Archive section + uncapped album handling on gallery page"
```

---

## Self-Review

**Spec coverage:**
- Uncap the two albums → Task 4 (policy) + Task 5 (serializer cap) + Tasks 8–9 (UI). ✓
- Detect by caption (UPPERCASE prefix, whole-word) → Task 1. ✓
- Move matches into Archive → Task 3 (`partition_archive`). ✓
- Archive read-only + excluded from build → Task 6 (build exclusion) + Tasks 7–9 (read-only UI). ✓
- Drop media-less posts → Task 6. ✓
- `inventory/archive.py`, model fields, parser call, policy, serializer, builder, UI → Tasks 1–9. ✓
- Tests per spec (archive matchers, parser, policy, serializer, builder, fixture, frontend) → Tasks 1–8. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code; every command has expected output. ✓

**Type consistency:** `is_special_album` / `archive_tag` / `partition_archive` signatures match across Tasks 1/3/6. `max_per_album` (album, nullable) is produced in Task 5 and consumed in Tasks 8–9. `archive` payload key produced in Task 5, consumed in Tasks 8–9. `selectable` prop added in Task 7 (PhotoTile/PhotoGrid/PhotoPreview) and used in Task 9. `archiveCount` prop added in Task 8, passed in Task 9. `'__archive__'` sentinel consistent across Tasks 8–9. ✓

**Known intentional cross-task FAIL:** Task 4 Step 6 fails until Task 5 lands (documented in the step); re-run green in Task 5 Step 4.
