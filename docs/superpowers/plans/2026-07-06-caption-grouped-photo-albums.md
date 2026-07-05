# Caption-grouped photo_albums Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-cluster the kept photos of `Mobile uploads` & `Photos` by caption into real `photo_album`s — each multi-photo group gets its own media subdirectory and album JSON in the build; single-photo captions become unanchored media.

**Architecture:** A new pure module `inventory/grouping.py` clusters identical captions and, for the two uncapped albums, replaces them with derived `Album`s (synthetic id = first photo's fbid) and moves singletons to the non-album bucket, tagging each moved/regrouped photo with a `ready_uri`. `build_inventory` runs it right after `partition_archive`, so UI and build agree. The builder copies each photo to its `ready_uri`, synthesizes a per-group album JSON, skips the original special-album JSONs, and rewrites feed uris so the downstream ETL derives one `photo_album` per group from the media path.

**Tech Stack:** Python 3.13 (FastAPI, Pydantic v2, pytest) via `uv`; SvelteKit (Svelte 5 runes, Skeleton v3 / Tailwind v4) with Vitest.

## Global Constraints

- Backend tests: `UV_LINK_MODE=copy uv run --no-sync pytest -q`.
- Lint: `uv run ruff check .` — line length 100, E501 not enforced.
- Frontend tests: from `frontend/`, `npm run test -- --run`.
- **Never glob `posts/media/`** (~875 MB) — drive off JSON, verify specific files.
- Grouping runs **after** archiving; it only sees kept (non-archived) photos.
- Special albums = normalized name ∈ `{"mobile uploads", "photos"}`; they are the ones `partition_archive` marked `uncapped=True`.
- Synthetic album id = the group's **first photo's `fbid`** (original album order).
- Media slug = `<AlnumHeadline≤30>_<synthId>`; the trailing id must be recoverable by `album_id_from_uri`.
- Singletons / no-caption photos → **unanchored**: `album_fbid=None`, loose `ready_uri` `posts/media/<fbid>.jpg`, appended to `non_album_photos` (auto-kept).
- Derived albums are **uncapped**.
- Original export is read-only; only the `ready/` layout changes.
- Spec: `docs/superpowers/specs/2026-07-06-caption-grouped-photo-albums-design.md`.

---

## File Structure

**Backend (create):**
- `src/streamlinify/inventory/grouping.py` — `caption_headline`, `media_slug`, `derive_caption_albums`.
- `tests/inventory/test_grouping.py` — unit tests.

**Backend (modify):**
- `src/streamlinify/inventory/models.py` — `Album.origin`, `Album.media_slug`, `Photo.ready_uri`.
- `src/streamlinify/inventory/parser.py` — call `derive_caption_albums` after `partition_archive`.
- `src/streamlinify/web/serializers.py` — album `origin`.
- `src/streamlinify/transform/builder.py` — copy to `ready_uri`, per-group album JSONs, skip special source albums, rewrite feed uris.
- `tests/conftest.py` — new `grouping_export_root` fixture.
- `tests/inventory/test_models.py`, `tests/inventory/test_archive.py`, `tests/inventory/test_parser.py`, `tests/web/test_serializers.py`, `tests/web/test_gallery_routes.py`, `tests/transform/test_builder.py` — extend / refactor.

**Frontend (modify):**
- `frontend/src/lib/components/AlbumList.svelte` — origin subheader.
- `frontend/src/lib/components/AlbumList.test.js` — extend.

---

### Task 1: Headline + media-slug helpers

**Files:**
- Create: `src/streamlinify/inventory/grouping.py`
- Test: `tests/inventory/test_grouping.py`

**Interfaces:**
- Produces: `caption_headline(caption: str) -> str`, `media_slug(headline: str, synth_id: str) -> str`.

- [ ] **Step 1: Write the failing test**

Create `tests/inventory/test_grouping.py`:

```python
from streamlinify.inventory.grouping import caption_headline, media_slug
from streamlinify.inventory.parser import album_id_from_uri


def test_caption_headline():
    assert caption_headline("HEADLINE ONE\n\nBody one.") == "HEADLINE ONE"
    assert caption_headline("  Solo line  ") == "Solo line"
    assert caption_headline("PEP-ARING 🔥\n\nHAPPENING NOW: x") == "PEP-ARING 🔥"
    assert caption_headline("x" * 150) == "x" * 100


def test_media_slug_shape_and_recoverable_id():
    assert media_slug("HEADLINE ONE", "g01") == "HEADLINEONE_g01"
    slug = media_slug("HEADLINE ONE", "999")
    assert album_id_from_uri(f"posts/media/{slug}/999.jpg") == "999"
    # headline with no alphanumerics falls back but keeps a recoverable id
    assert album_id_from_uri(f"posts/media/{media_slug('🔥', '42')}/42.jpg") == "42"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/inventory/test_grouping.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'streamlinify.inventory.grouping'`.

- [ ] **Step 3: Create the module**

Create `src/streamlinify/inventory/grouping.py`:

```python
from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")


def caption_headline(caption: str) -> str:
    """The caption's first non-empty line, trimmed and truncated to 100 chars."""
    for line in caption.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:100]
    return caption.strip()[:100]


def media_slug(headline: str, synth_id: str) -> str:
    """`<AlnumHeadline≤30>_<synthId>` — the per-group media subdir name.

    The trailing `_<synthId>` mirrors FB's `<Album>_<albumFbid>` so the downstream
    ETL (and our own `album_id_from_uri`) recovers the synthetic id from the path.
    """
    alnum = _NON_ALNUM.sub("", headline)[:30] or "album"
    return f"{alnum}_{synth_id}"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/inventory/test_grouping.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/streamlinify/inventory/grouping.py tests/inventory/test_grouping.py
git commit -m "feat(inventory): caption headline + media-slug helpers"
```

---

### Task 2: Model fields for grouping

**Files:**
- Modify: `src/streamlinify/inventory/models.py`
- Test: `tests/inventory/test_models.py`

**Interfaces:**
- Produces: `Album.origin: str | None`, `Album.media_slug: str | None`, `Photo.ready_uri: str | None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/inventory/test_models.py`:

```python
def test_grouping_field_defaults():
    p = _photo("p1", album_fbid="111")
    assert p.ready_uri is None
    a = Album(fb_album_id="111", name="A")
    assert a.origin is None
    assert a.media_slug is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/inventory/test_models.py::test_grouping_field_defaults -q`
Expected: FAIL — `AttributeError: 'Photo' object has no attribute 'ready_uri'`.

- [ ] **Step 3: Add the fields**

In `src/streamlinify/inventory/models.py`, add to `Photo` (after `archive_tag`):

```python
    archive_tag: str | None = None  # the matched keyword, e.g. "BREAKING"
    ready_uri: str | None = None  # dest path (from posts/) in the ready folder; None = copy in place
```

Add to `Album` (after `uncapped`):

```python
    uncapped: bool = False  # True for the special dump albums (no per-album cap)
    origin: str | None = None  # parent dump name for a derived caption-album (UI subheader)
    media_slug: str | None = None  # derived album's media subdir "<slug>_<id>"; None for FB albums
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/inventory/test_models.py -q`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add src/streamlinify/inventory/models.py tests/inventory/test_models.py
git commit -m "feat(inventory): origin/media_slug/ready_uri fields for grouping"
```

---

### Task 3: derive_caption_albums (pure)

**Files:**
- Modify: `src/streamlinify/inventory/grouping.py`
- Test: `tests/inventory/test_grouping.py`

**Interfaces:**
- Consumes: `caption_headline`, `media_slug` (Task 1); model fields (Task 2).
- Produces: `derive_caption_albums(inventory: ExportInventory) -> None` (mutates in place).

- [ ] **Step 1: Write the failing test**

Append to `tests/inventory/test_grouping.py`:

```python
from streamlinify.inventory.grouping import derive_caption_albums
from streamlinify.inventory.models import Album, ExportInventory, Photo


def _p(fbid, caption, album="777"):
    return Photo(
        fbid=fbid,
        original_uri=f"posts/media/Mobileuploads_777/{fbid}.jpg",
        resolved_path=f"posts/media/Mobileuploads_777/{fbid}.jpg",
        caption=caption,
        album_fbid=album,
    )


def test_derive_groups_unanchors_and_skips_normal_albums():
    special = Album(
        fb_album_id="777", name="Mobile uploads", uncapped=True,
        photos=[_p("g01", "H1\n\nb"), _p("g02", "H1\n\nb"), _p("s01", "Solo"), _p("n01", None)],
    )
    normal = Album(
        fb_album_id="111", name="Animo Fest",
        photos=[_p("a01", "H1\n\nb", "111")],
    )
    inv = ExportInventory(albums=[special, normal])
    derive_caption_albums(inv)

    by_id = {a.fb_album_id: a for a in inv.albums}
    # special album replaced by one derived album (the 2-photo group)
    assert "777" not in by_id
    assert by_id["g01"].name == "H1"
    assert by_id["g01"].origin == "Mobile uploads"
    assert by_id["g01"].uncapped is True
    assert by_id["g01"].media_slug == "H1_g01"
    assert {p.fbid for p in by_id["g01"].photos} == {"g01", "g02"}
    assert by_id["g01"].photos[0].album_fbid == "g01"
    assert by_id["g01"].photos[0].ready_uri == "posts/media/H1_g01/g01.jpg"

    # singleton + no-caption become unanchored non-album photos
    na = {p.fbid: p for p in inv.non_album_photos}
    assert set(na) == {"s01", "n01"}
    assert na["s01"].album_fbid is None
    assert na["s01"].ready_uri == "posts/media/s01.jpg"

    # a non-uncapped album with the same caption is left untouched
    assert by_id["111"].uncapped is False
    assert {p.fbid for p in by_id["111"].photos} == {"a01"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/inventory/test_grouping.py::test_derive_groups_unanchors_and_skips_normal_albums -q`
Expected: FAIL — `ImportError: cannot import name 'derive_caption_albums'`.

- [ ] **Step 3: Implement `derive_caption_albums`**

Append to `src/streamlinify/inventory/grouping.py` (add the import at the top of the file too):

```python
from collections import OrderedDict

from .models import Album, ExportInventory, Photo
```

```python
def derive_caption_albums(inventory: ExportInventory) -> None:
    """Cluster the two uncapped dumps' photos by caption into real photo_albums.

    For each `uncapped` album: photos sharing a non-empty caption form a derived album
    (synthetic id = the group's first photo fbid, name = the caption headline). Groups
    of one, and any no-caption photo, become unanchored — moved to `non_album_photos`
    with a loose `ready_uri`. Non-uncapped albums pass through unchanged. Derived albums
    are inserted where the parent was, contiguous, so the UI can subhead them.
    """
    new_albums: list[Album] = []
    for album in inventory.albums:
        if not album.uncapped:
            new_albums.append(album)
            continue

        groups: "OrderedDict[str, list[Photo]]" = OrderedDict()
        loose: list[Photo] = []
        for photo in album.photos:
            key = (photo.caption or "").strip()
            if key:
                groups.setdefault(key, []).append(photo)
            else:
                loose.append(photo)

        for key, members in groups.items():
            if len(members) < 2:
                loose.extend(members)
                continue
            synth = members[0].fbid
            headline = caption_headline(key)
            slug = media_slug(headline, synth)
            for photo in members:
                photo.album_fbid = synth
                photo.ready_uri = f"posts/media/{slug}/{photo.fbid}.jpg"
            new_albums.append(
                Album(
                    fb_album_id=synth, name=headline, origin=album.name,
                    uncapped=True, media_slug=slug, photos=members,
                )
            )

        for photo in loose:
            photo.album_fbid = None
            photo.ready_uri = f"posts/media/{photo.fbid}.jpg"
            inventory.non_album_photos.append(photo)

    inventory.albums = new_albums
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/inventory/test_grouping.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/streamlinify/inventory/grouping.py tests/inventory/test_grouping.py
git commit -m "feat(inventory): derive caption-albums, unanchor singletons"
```

---

### Task 4: Serialize album origin

**Files:**
- Modify: `src/streamlinify/web/serializers.py`
- Test: `tests/web/test_serializers.py`

**Interfaces:**
- Consumes: `Album.origin` (Task 2).
- Produces: each album dict gains `"origin": a.origin`.

- [ ] **Step 1: Write the failing test**

Append to `tests/web/test_serializers.py`:

```python
def test_payload_includes_album_origin(tmp_path):
    inv = ExportInventory(
        albums=[
            Album(
                fb_album_id="g01", name="HEADLINE ONE", origin="Mobile uploads",
                uncapped=True, media_slug="HEADLINEONE_g01",
                photos=[Photo(fbid="g01", original_uri="x", resolved_path="x",
                              caption="c", exists=True, album_fbid="g01")],
            ),
            Album(fb_album_id="111", name="Animo Fest", photos=[]),
        ],
    )
    sel = SelectionState(tmp_path / "sel.json", DefaultPolicy())
    payload = inventory_payload("e", inv, sel, 10)

    origins = {a["name"]: a["origin"] for a in payload["albums"]}
    assert origins["HEADLINE ONE"] == "Mobile uploads"
    assert origins["Animo Fest"] is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/web/test_serializers.py::test_payload_includes_album_origin -q`
Expected: FAIL — `KeyError: 'origin'`.

- [ ] **Step 3: Add `origin` to the album dict**

In `src/streamlinify/web/serializers.py`, inside the `albums = [ {...} for a in inventory.albums ]` comprehension, add the `origin` key next to `name`:

```python
            "fb_album_id": a.fb_album_id,
            "name": a.name,
            "origin": a.origin,
            "count_selected": selection.count(a.fb_album_id),
            "max_per_album": None if a.uncapped else max_per_album,
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/web/test_serializers.py -q`
Expected: PASS (all tests — existing ones unaffected; they check specific keys, not full-dict equality).

- [ ] **Step 5: Commit**

```bash
git add src/streamlinify/web/serializers.py tests/web/test_serializers.py
git commit -m "feat(web): serialize album origin"
```

---

### Task 5: Wire grouping into the parser (+ fixture, refactor archive tests)

**Files:**
- Modify: `src/streamlinify/inventory/parser.py`
- Modify: `tests/conftest.py` (new `grouping_export_root`)
- Modify: `tests/inventory/test_parser.py` (replace archive-parser test with grouping test)
- Modify: `tests/inventory/test_archive.py` (add isolated `partition_archive` unit test)
- Modify: `tests/web/test_gallery_routes.py` (retarget uncapped test to grouping fixture)

**Interfaces:**
- Consumes: `derive_caption_albums` (Task 3); `partition_archive` (existing).
- Produces: `build_inventory` output now has derived albums + unanchored singletons; pytest fixture `grouping_export_root` returning a `Path` (special album `Mobile uploads` fbid `777`, normal `Animo Fest` fbid `111`).

- [ ] **Step 1: Add the `grouping_export_root` fixture**

Append to `tests/conftest.py`:

```python
@pytest.fixture
def grouping_export_root(tmp_path: Path) -> Path:
    """Special album with a 2-photo group, a 3-photo group, a singleton, a no-caption
    photo, and a news-tag photo (archived first); plus a normal album sharing a caption."""
    root = tmp_path / "grouping_export"
    media = root / "posts" / "media"
    album_dir = root / "posts" / "album"
    album_dir.mkdir(parents=True)

    u_ids = ["g01", "g02", "g03", "g04", "g05", "s01", "n01", "t01"]
    u_photos = [_photo_record("Mobileuploads_777", f, f.upper()) for f in u_ids]
    (album_dir / "0.json").write_text(
        json.dumps({"name": "Mobile uploads", "photos": u_photos}), encoding="utf-8"
    )
    for f in u_ids:
        _img(media / "Mobileuploads_777" / f"{f}.jpg")

    (album_dir / "1.json").write_text(
        json.dumps({"name": "Animo Fest", "photos": [_photo_record("AnimoFest_111", "a01", "A1")]}),
        encoding="utf-8",
    )
    _img(media / "AnimoFest_111" / "a01.jpg")

    def att(*fbids):
        return [{"data": [{"media": _photo_record("Mobileuploads_777", f, f.upper())}]} for f in fbids]

    posts = [
        {"data": [{"post": "HEADLINE ONE\n\nBody one."}], "attachments": att("g01", "g02")},
        {"data": [{"post": "HEADLINE TWO\n\nBody two."}], "attachments": att("g03", "g04", "g05")},
        {"data": [{"post": "Solo headline\n\nSolo body."}], "attachments": att("s01")},
        {"data": [{"post": "BREAKING: fire"}], "attachments": att("t01")},
        # a01 lives in a non-special album but shares HEADLINE ONE's caption
        {"data": [{"post": "HEADLINE ONE\n\nBody one."}],
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

- [ ] **Step 2: Replace the archive-parser test with a grouping-parser test**

In `tests/inventory/test_parser.py`, **delete** `test_build_inventory_partitions_archive` (its Mobile-uploads/Photos assertions no longer hold once grouping runs) and add:

```python
def test_build_inventory_groups_captions(grouping_export_root: Path):
    inv = build_inventory(grouping_export_root)
    by_id = {a.fb_album_id: a for a in inv.albums}

    # archive still runs first
    assert {p.fbid for p in inv.archived_photos} == {"t01"}

    # special album replaced by its derived caption-albums
    assert "777" not in by_id
    assert by_id["g01"].name == "HEADLINE ONE"
    assert by_id["g01"].origin == "Mobile uploads"
    assert by_id["g01"].uncapped is True
    assert by_id["g01"].media_slug == "HEADLINEONE_g01"
    assert {p.fbid for p in by_id["g01"].photos} == {"g01", "g02"}
    assert by_id["g01"].photos[0].ready_uri == "posts/media/HEADLINEONE_g01/g01.jpg"
    assert {p.fbid for p in by_id["g03"].photos} == {"g03", "g04", "g05"}

    # singleton + no-caption → unanchored non-album photos
    na = {p.fbid: p for p in inv.non_album_photos}
    assert set(na) == {"s01", "n01"}
    assert na["s01"].album_fbid is None
    assert na["s01"].ready_uri == "posts/media/s01.jpg"

    # non-special album with the same caption stays capped and untouched
    assert by_id["111"].uncapped is False
    assert {p.fbid for p in by_id["111"].photos} == {"a01"}
```

- [ ] **Step 3: Add an isolated `partition_archive` unit test**

In `tests/inventory/test_archive.py`, add (preserves archive coverage now that the parser test is grouping-focused):

```python
def test_partition_archive_sets_aside_tagged():
    from streamlinify.inventory.archive import partition_archive
    from streamlinify.inventory.models import Album, ExportInventory, Photo

    def p(fbid, caption, album):
        return Photo(fbid=fbid, original_uri="x", resolved_path="x", caption=caption, album_fbid=album)

    inv = ExportInventory(
        albums=[
            Album(fb_album_id="555", name="Mobile uploads",
                  photos=[p("u01", "BREAKING: x", "555"), p("u02", "hello", "555")]),
            Album(fb_album_id="111", name="Animo Fest", photos=[p("a01", "BREAKING: y", "111")]),
        ]
    )
    partition_archive(inv)

    by_id = {a.fb_album_id: a for a in inv.albums}
    assert by_id["555"].uncapped is True
    assert {x.fbid for x in by_id["555"].photos} == {"u02"}
    assert {x.fbid for x in inv.archived_photos} == {"u01"}
    # tag caption in a non-special album is left alone
    assert by_id["111"].uncapped is False
    assert {x.fbid for x in by_id["111"].photos} == {"a01"}
```

- [ ] **Step 4: Retarget the uncapped route test to the grouping fixture**

In `tests/web/test_gallery_routes.py`, **replace** `test_inventory_marks_special_albums_uncapped` with:

```python
def test_inventory_exposes_derived_uncapped_albums(grouping_export_root, tmp_path, monkeypatch):
    client = _loaded_client(grouping_export_root, tmp_path, monkeypatch)
    body = client.get("/api/inventory").json()

    derived = [a for a in body["albums"] if a["origin"] == "Mobile uploads"]
    assert {a["name"] for a in derived} == {"HEADLINE ONE", "HEADLINE TWO"}
    assert all(a["max_per_album"] is None for a in derived)
    assert {p["fbid"] for p in body["archive"]} == {"t01"}
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/inventory/test_parser.py::test_build_inventory_groups_captions tests/web/test_gallery_routes.py::test_inventory_exposes_derived_uncapped_albums -q`
Expected: FAIL — grouping not wired into `build_inventory` yet (special album `777` still present, no derived albums).

- [ ] **Step 6: Wire `derive_caption_albums` into the parser**

In `src/streamlinify/inventory/parser.py`, add the import:

```python
from .archive import partition_archive
from .grouping import derive_caption_albums
from .models import Album, ExportInventory, Photo
```

and update the tail of `build_inventory`:

```python
    inventory = ExportInventory(albums=albums, non_album_photos=non_album)
    partition_archive(inventory)
    derive_caption_albums(inventory)
    return inventory
```

- [ ] **Step 7: Run the parser + archive + gallery tests**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/inventory/test_parser.py tests/inventory/test_archive.py tests/web/test_gallery_routes.py -q`
Expected: PASS (grouping test, isolated archive test, retargeted route test, and the rest).

- [ ] **Step 8: Run the full backend suite (expect green)**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest -q`
Expected: PASS. The builder is not reworked yet, so it still copies by `original_uri` and ignores `ready_uri` — the archive builder test's `Mobileuploads_555/u02.jpg` assertion still holds. (That assertion is what Task 6 updates to the loose path once the builder honors `ready_uri`.)

- [ ] **Step 9: Commit**

```bash
git add src/streamlinify/inventory/parser.py tests/conftest.py tests/inventory/test_parser.py tests/inventory/test_archive.py tests/web/test_gallery_routes.py
git commit -m "feat(inventory): run caption grouping in build_inventory"
```

---

### Task 6: Build real photo_albums

**Files:**
- Modify: `src/streamlinify/transform/builder.py`
- Test: `tests/transform/test_builder.py`

**Interfaces:**
- Consumes: `Album.media_slug`, `Photo.ready_uri` (Task 2); `is_special_album` (existing); grouping in `build_inventory` (Task 5).
- Produces: `build_ready_folder` copies to `ready_uri`, writes a per-group album JSON, skips original special-album JSONs, rewrites feed uris.

- [ ] **Step 1: Write the failing test**

Append to `tests/transform/test_builder.py`:

```python
def test_build_writes_caption_albums(grouping_export_root: Path, tmp_path: Path):
    from streamlinify.inventory.parser import build_inventory

    dest = tmp_path / "ready"
    inv = build_inventory(grouping_export_root)
    keep = {p.fbid for p in inv.all_photos() if p.exists}  # keep all present (archived subtracted by builder)
    build_ready_folder(grouping_export_root, dest, keep)

    media = dest / "posts" / "media"
    album = dest / "posts" / "album"

    # derived group: media in a fresh <slug>_<id>/ subdir + a per-group album JSON
    assert (media / "HEADLINEONE_g01" / "g01.jpg").exists()
    assert (media / "HEADLINEONE_g01" / "g02.jpg").exists()
    assert not (media / "Mobileuploads_777" / "g01.jpg").exists()  # not at original path
    grp = json.loads((album / "g01.json").read_text(encoding="utf-8"))
    assert grp["name"] == "HEADLINE ONE"
    assert {Path(p["uri"]).stem for p in grp["photos"]} == {"g01", "g02"}
    assert all("HEADLINEONE_g01/" in p["uri"] for p in grp["photos"])

    # singleton + no-caption: loose media, no album subdir, no album JSON
    assert (media / "s01.jpg").exists()
    assert (media / "n01.jpg").exists()

    # original special-album JSON is not carried over; normal album is
    assert not (album / "0.json").exists()
    assert (album / "1.json").exists()
    assert (media / "AnimoFest_111" / "a01.jpg").exists()

    # archived excluded
    assert not (media / "Mobileuploads_777" / "t01.jpg").exists()

    # feed uris rewritten to the new paths; fully-archived post dropped
    posts = json.loads((dest / "posts" / "profile_posts_1.json").read_text(encoding="utf-8"))
    uris = [d["media"]["uri"] for post in posts for att in post.get("attachments", []) for d in att.get("data", [])]
    assert any("HEADLINEONE_g01/g01.jpg" in u for u in uris)
    assert any(u.endswith("posts/media/s01.jpg") for u in uris)
    bodies = [d["post"] for post in posts for d in post.get("data", []) if "post" in d]
    assert "BREAKING: fire" not in bodies
```

Also **update** the existing `test_build_excludes_archived_and_drops_empty_posts`: `u02` is now unanchored (loose), so change its kept-media assertion from the old subdir path to the loose path:

```python
    # Non-archived kept photos are copied (u02 is now unanchored → loose path).
    assert (dest / "posts" / "media" / "u02.jpg").exists()
```

(Replace the previous `assert (dest / "posts" / "media" / "Mobileuploads_555" / "u02.jpg").exists()` line.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/transform/test_builder.py -q`
Expected: FAIL — the old builder copies by original path (no `HEADLINEONE_g01/`), writes no per-group JSON, and still emits `0.json`.

- [ ] **Step 3: Rework the builder**

Replace the body of `src/streamlinify/transform/builder.py` from the imports down through `build_ready_folder` with:

```python
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..inventory.archive import is_special_album
from ..inventory.parser import build_inventory, photo_fbid, resolve_uri

DROP_JSON = {
    "videos.json",
    "content_sharing_links_you_have_created.json",
    "edits_you_made_to_posts.json",
    "places_you_have_been_tagged_in.json",
}


@dataclass
class BuildResult:
    ready_root: Path
    copied: int
    albums_written: int
    orphans: list[str]


def _rel_from_posts(uri: str) -> str:
    idx = uri.find("posts/")
    return uri[idx:] if idx != -1 else uri


def _copy_media(photo, export_root: Path, dest: Path) -> bool:
    src = resolve_uri(photo.original_uri, export_root)
    if not src.exists():
        return False
    rel = photo.ready_uri or _rel_from_posts(photo.original_uri)
    target = dest / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    return True


def _album_photo_record(photo) -> dict:
    rec: dict = {"uri": photo.ready_uri}
    if photo.creation_at is not None:
        rec["creation_timestamp"] = int(photo.creation_at.timestamp())
    if photo.title:
        rec["title"] = photo.title
    return rec


def build_ready_folder(export_root: Path, dest: Path, keep_fbids: set[str]) -> BuildResult:
    inventory = build_inventory(export_root)
    # Archived (news-caption) photos are set aside — never carried into the build,
    # even if a stale selection.json still names one.
    keep_fbids = keep_fbids - {p.fbid for p in inventory.archived_photos}
    dest.mkdir(parents=True, exist_ok=True)

    copied = 0
    orphans: list[str] = []
    for photo in inventory.all_photos():
        if photo.fbid not in keep_fbids:
            continue
        if _copy_media(photo, export_root, dest):
            copied += 1
        else:
            orphans.append(photo.original_uri)

    present_fbids = {
        p.fbid for p in inventory.all_photos() if p.fbid in keep_fbids and p.exists
    }

    album_dst_dir = dest / "posts" / "album"
    albums_written = 0

    # Derived caption-albums: synthesize a fresh album JSON per group, pointing at the
    # regrouped media subdir.
    for album in inventory.albums:
        if album.media_slug is None:
            continue
        kept = [p for p in album.photos if p.fbid in keep_fbids and p.exists]
        if not kept:
            continue
        album_dst_dir.mkdir(parents=True, exist_ok=True)
        (album_dst_dir / f"{album.fb_album_id}.json").write_text(
            json.dumps(
                {"name": album.name, "photos": [_album_photo_record(p) for p in kept]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        albums_written += 1

    # Original FB albums: filter to kept photos, but skip the special dumps — they are
    # replaced by the derived caption-albums above.
    album_src_dir = export_root / "posts" / "album"
    for album_path in sorted(album_src_dir.glob("*.json")):
        raw = json.loads(album_path.read_text(encoding="utf-8"))
        if is_special_album(raw.get("name", "")):
            continue
        kept = [p for p in raw.get("photos", []) if photo_fbid(p["uri"]) in keep_fbids]
        if not kept:
            continue
        album_dst_dir.mkdir(parents=True, exist_ok=True)
        out = dict(raw)
        out["photos"] = kept
        (album_dst_dir / album_path.name).write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        albums_written += 1

    # profile_posts: keep only present media, rewrite regrouped/loosened uris so the feed
    # and album files agree on the path-derived fb_album_id, then drop media-less posts.
    ready_uris = {p.fbid: p.ready_uri for p in inventory.all_photos() if p.ready_uri}
    posts_path = export_root / "posts" / "profile_posts_1.json"
    if posts_path.exists():
        posts = json.loads(posts_path.read_text(encoding="utf-8"))
        for post in posts:
            for att in post.get("attachments", []):
                kept_data = []
                for d in att.get("data", []):
                    if "media" not in d:
                        continue
                    fbid = photo_fbid(d["media"]["uri"])
                    if fbid not in present_fbids:
                        continue
                    if fbid in ready_uris:
                        d["media"]["uri"] = ready_uris[fbid]
                    kept_data.append(d)
                att["data"] = kept_data
            post["attachments"] = [att for att in post.get("attachments", []) if att["data"]]
        posts = [post for post in posts if post.get("attachments")]
        (dest / "posts").mkdir(parents=True, exist_ok=True)
        (dest / "posts" / "profile_posts_1.json").write_text(
            json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return BuildResult(ready_root=dest, copied=copied, albums_written=albums_written, orphans=orphans)
```

- [ ] **Step 4: Run the builder tests to verify they pass**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/transform/test_builder.py -q`
Expected: PASS — the new grouping build test, the updated archive-exclusion test, and the unchanged `test_build_filtered_mirror` / `test_idempotent_rerun` (export_root has no special albums, so `ready_uri` is all `None` → identical behavior).

- [ ] **Step 5: Run the full backend suite + lint**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest -q && uv run ruff check .`
Expected: PASS (all backend tests) and `All checks passed!`.

- [ ] **Step 6: Commit**

```bash
git add src/streamlinify/transform/builder.py tests/transform/test_builder.py
git commit -m "feat(transform): build caption-grouped photo_albums + loose singletons"
```

---

### Task 7: Origin subheader in the album rail

**Files:**
- Modify: `frontend/src/lib/components/AlbumList.svelte`
- Test: `frontend/src/lib/components/AlbumList.test.js`

**Interfaces:**
- Consumes: `album.origin` from the API.
- Produces: `AlbumList` renders a small uppercase subheader before the first album of each `origin` run.

- [ ] **Step 1: Write the failing test**

Append a test inside the `describe('AlbumList', ...)` block in `frontend/src/lib/components/AlbumList.test.js`:

```javascript
	it('renders an origin subheader for derived albums', () => {
		const withOrigin = [
			{ fb_album_id: '111', name: 'Animo Fest', count_selected: 0, max_per_album: 10, origin: null },
			{ fb_album_id: 'g01', name: 'HEADLINE ONE', count_selected: 0, max_per_album: null, origin: 'Mobile uploads' },
			{ fb_album_id: 'g03', name: 'HEADLINE TWO', count_selected: 0, max_per_album: null, origin: 'Mobile uploads' }
		];
		render(AlbumList, {
			props: { albums: withOrigin, nonAlbumCount: 0, archiveCount: 0, activeId: '111', onSelect: vi.fn() }
		});
		expect(screen.getByText('Mobile uploads')).toBeInTheDocument();
		expect(screen.getByText('HEADLINE ONE')).toBeInTheDocument();
		expect(screen.getByText('HEADLINE TWO')).toBeInTheDocument();
	});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm run test -- --run AlbumList`
Expected: FAIL — no element with text `Mobile uploads` (no subheader rendered).

- [ ] **Step 3: Add the origin subheader**

In `frontend/src/lib/components/AlbumList.svelte`, change the album loop to expose the index and emit a subheader when the `origin` run starts. Replace the `{#each albums as a (a.fb_album_id)}` opening line with:

```svelte
	{#each albums as a, i (a.fb_album_id)}
		{#if a.origin && a.origin !== albums[i - 1]?.origin}
			<p class="px-2 pb-0.5 pt-2 text-[0.65rem] font-semibold uppercase tracking-wide text-surface-400">
				{a.origin}
			</p>
		{/if}
```

(The rest of the loop body — the album `<button>` — is unchanged. The existing `{#each ... }` block already closes with `{/each}`.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm run test -- --run AlbumList`
Expected: PASS (all AlbumList tests — the existing two pass `origin: undefined`, so `a.origin && …` is falsy and no subheader renders for them).

- [ ] **Step 5: Run the full frontend suite + production build**

Run: `cd frontend && npm run test -- --run && npm run build`
Expected: all Vitest tests PASS; `npm run build` completes with no Svelte errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/components/AlbumList.svelte frontend/src/lib/components/AlbumList.test.js
git commit -m "feat(ui): origin subheader for derived caption-albums"
```

---

## Self-Review

**Spec coverage:**
- Auto-derive by identical caption → Task 3 (`derive_caption_albums`). ✓
- Scope = kept non-archived in the two uncapped albums → Task 3 (guards on `album.uncapped`) + Task 5 (order: archive then group). ✓
- Write real photo_albums (per-group media subdir + album JSON) → Task 6. ✓
- Synthetic id = first photo fbid; media slug recoverable → Tasks 1, 3. ✓
- Singletons/no-caption → unanchored loose media → Tasks 3 (inventory) + 6 (loose copy). ✓
- Feed-uri rewrite for path agreement → Task 6. ✓
- Uncapped derived albums → Task 3 (`uncapped=True`) + existing policy/serializer. ✓
- Origin subheader UI → Task 7. ✓
- Model fields, parser wiring, serializer origin, fixture, test refactors → Tasks 2, 4, 5. ✓

**Placeholder scan:** No TBD/TODO; every code step is complete; commands have expected output. The one intentional ambiguity (Task 5 Step 8) is explicitly labelled and resolved in Task 6. ✓

**Type consistency:** `caption_headline`/`media_slug`/`derive_caption_albums` signatures match across Tasks 1/3/5/6. `Album.origin`/`Album.media_slug`/`Photo.ready_uri` defined in Task 2, consumed in Tasks 3/4/6/7. `media_slug` output `"HEADLINEONE_g01"` is consistent between the grouping test (Task 3), parser test (Task 5), and builder test (Task 6). Derived album JSON filename `f"{album.fb_album_id}.json"` (Task 6) = `g01.json`, matching the test. ✓
