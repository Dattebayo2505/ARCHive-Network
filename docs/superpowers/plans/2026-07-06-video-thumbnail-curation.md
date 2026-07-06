# Video Thumbnail Curation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop importing video `.mp4` files; instead replace each video with a user-chosen still frame (captured in the browser), auto-keep every video for the build, and give the volunteer a video-preview picker to choose the frame.

**Architecture:** The parser splits videos out of the invisible non-album bucket into a new `inventory.videos` category. New backend endpoints stream the raw `.mp4` for playback and store/serve a per-video still under `workspace/thumbs/videos/<fbid>.jpg`. The frontend adds a "Videos" gallery category whose tiles open a `VideoPreview` picker; a `<canvas>` grabs the current frame and POSTs it. The builder copies the still (never the `.mp4`) into the output and rewrites the feed URI from `.mp4` to `.jpg`.

**Tech Stack:** FastAPI (uv) backend, Pillow (photos only — videos never touch PIL), SvelteKit 5 + Skeleton v3/Tailwind v4 frontend, Vitest + pytest.

## Global Constraints

- Backend line-length 100; E501 not enforced. Run lint with `uv run ruff check .`.
- Backend tests: `UV_LINK_MODE=copy uv run --no-sync pytest <path> -q` (src is on pythonpath; `--no-sync` skips reinstall).
- Frontend tests: `cd frontend && npm run test -- <file>` (`vitest run`).
- Never glob `posts/media/` — drive off JSON, then verify the specific file exists.
- Business logic lives in modules; `web/` routers stay thin.
- The original export is read-only; all generated state lives under `workspace/` (gitignored).
- No new backend runtime dependency (no ffmpeg): thumbnails are captured client-side via canvas.
- Video detection is by URI extension: `.mp4`, `.mov`, `.webm`.
- The UI is deliberately light-only; do not add dark-mode variants.
- Kill the dev server port before rerunning Node: `npx kill-port 3000` (see `kill-server.ps1`).

---

## File Structure

**Backend**
- `src/streamlinify/inventory/models.py` — add `Photo.is_video`; add `ExportInventory.videos`.
- `src/streamlinify/inventory/parser.py` — `is_video_uri()`; route videos to `inventory.videos`.
- `src/streamlinify/thumbnails/video_store.py` — **new**: `VideoThumbnailStore` (save/get/has a still).
- `src/streamlinify/web/session.py` — add `video_thumbs: VideoThumbnailStore` to `Session`.
- `src/streamlinify/web/routes_ingest.py` — construct the store in `_start_session`.
- `src/streamlinify/web/routes_video.py` — **new**: stream mp4, save/get still.
- `src/streamlinify/app.py` — register the video router.
- `src/streamlinify/web/serializers.py` — add `videos` array to the inventory payload.
- `src/streamlinify/transform/builder.py` — copy stills (not mp4s), rewrite feed URIs, report skips.
- `src/streamlinify/transform/report.py` — surface videos built / skipped.
- `src/streamlinify/web/routes_build.py` — pass the store dir to the builder; include counts in the response.
- `tests/conftest.py` — **new** `video_export_root` fixture.

**Frontend**
- `frontend/src/lib/api.js` — `videoUrl`, `videoThumbUrl`, `saveVideoThumbnail`.
- `frontend/src/lib/videoThumbs.js` — **new**: `captureFrame`, `seedThumbnail`, `seedMissingThumbnails`.
- `frontend/src/lib/components/PhotoTile.svelte` — `video` mode (play badge, no checkmark, click = open, placeholder on 404).
- `frontend/src/lib/components/PhotoGrid.svelte` — pass `video` through.
- `frontend/src/lib/components/VideoPreview.svelte` — **new**: player + "Choose Thumbnail" + chosen-still panel.
- `frontend/src/lib/components/AlbumList.svelte` — "Videos" entry.
- `frontend/src/routes/gallery/+page.svelte` — Videos category, grid, context-menu swap, auto-seed on mount.

---

## Task 1: Video detection & `inventory.videos`

**Files:**
- Modify: `src/streamlinify/inventory/models.py`
- Modify: `src/streamlinify/inventory/parser.py`
- Modify: `tests/conftest.py` (add `video_export_root` fixture)
- Test: `tests/inventory/test_video_parser.py`

**Interfaces:**
- Produces: `Photo.is_video: bool`; `ExportInventory.videos: list[Photo]`; `parser.is_video_uri(uri: str) -> bool`.
- Consumes: existing `build_inventory(export_root) -> ExportInventory`.

- [ ] **Step 1: Add the `video_export_root` fixture**

In `tests/conftest.py`, append this fixture (uses the existing `_img`, `_photo_record`, `PREFIX` helpers):

```python
@pytest.fixture
def video_export_root(tmp_path: Path) -> Path:
    """A minimal export with one named album plus one video (mp4 on disk,
    referenced from profile_posts and listed in videos.json)."""
    root = tmp_path / "video_export"
    media = root / "posts" / "media"
    album_dir = root / "posts" / "album"
    album_dir.mkdir(parents=True)

    (album_dir / "0.json").write_text(
        json.dumps({"name": "Animo Fest", "photos": [_photo_record("AnimoFest_111", "a01", "Photo 1")]}),
        encoding="utf-8",
    )
    _img(media / "AnimoFest_111" / "a01.jpg")

    vid_uri = f"{PREFIX}/posts/media/videos/v01.mp4"
    (media / "videos").mkdir(parents=True)
    (media / "videos" / "v01.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42FAKEBYTES")

    posts = [
        {
            "data": [{"post": "Watch this clip #ARCH"}],
            "attachments": [{"data": [{"media": {"uri": vid_uri, "creation_timestamp": 1_700_000_500, "title": ""}}]}],
        },
        {
            "data": [{"post": "Great game"}],
            "attachments": [{"data": [{"media": _photo_record("AnimoFest_111", "a01", "Photo 1")}]}],
        },
    ]
    (root / "posts" / "profile_posts_1.json").write_text(json.dumps(posts), encoding="utf-8")
    (root / "posts" / "videos.json").write_text(
        json.dumps({"videos_v2": [{"uri": vid_uri, "creation_timestamp": 1_700_000_500, "title": "", "description": "Watch this clip"}]}),
        encoding="utf-8",
    )
    for name in (
        "content_sharing_links_you_have_created.json",
        "edits_you_made_to_posts.json",
        "places_you_have_been_tagged_in.json",
    ):
        (root / "posts" / name).write_text("[]", encoding="utf-8")

    return root
```

- [ ] **Step 2: Write the failing test**

Create `tests/inventory/test_video_parser.py`:

```python
from pathlib import Path

from streamlinify.inventory.parser import build_inventory, is_video_uri


def test_is_video_uri_by_extension():
    assert is_video_uri("posts/media/videos/x.mp4")
    assert is_video_uri("posts/media/videos/x.MOV")
    assert not is_video_uri("posts/media/AnimoFest_111/a01.jpg")


def test_videos_split_out_of_non_album(video_export_root: Path):
    inv = build_inventory(video_export_root)
    assert {v.fbid for v in inv.videos} == {"v01"}
    assert all(v.is_video for v in inv.videos)
    # the video must NOT leak into the auto-kept non-album bucket
    assert "v01" not in {p.fbid for p in inv.non_album_photos}
    # caption comes from the post body
    assert inv.videos[0].caption == "Watch this clip #ARCH"
    # a photo is still a photo
    assert any(not p.is_video for p in inv.all_photos())
```

- [ ] **Step 3: Run test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/inventory/test_video_parser.py -q`
Expected: FAIL (`cannot import name 'is_video_uri'`).

- [ ] **Step 4: Add `is_video` to the model**

In `src/streamlinify/inventory/models.py`, add the field to `Photo` (after `exists`):

```python
    is_video: bool = False  # True when the media is a video (mp4/mov/webm), not a photo
```

And add `videos` to `ExportInventory` and include it in `all_photos()`:

```python
class ExportInventory(BaseModel):
    albums: list[Album] = []
    non_album_photos: list[Photo] = []
    archived_photos: list[Photo] = []
    videos: list[Photo] = []

    def all_photos(self) -> list[Photo]:
        out: list[Photo] = [p for a in self.albums for p in a.photos]
        out.extend(self.non_album_photos)
        out.extend(self.archived_photos)
        out.extend(self.videos)
        return out
```

- [ ] **Step 5: Detect and route videos in the parser**

In `src/streamlinify/inventory/parser.py`, add near the top (after imports):

```python
_VIDEO_EXTS = {".mp4", ".mov", ".webm"}


def is_video_uri(uri: str) -> bool:
    return Path(uri).suffix.lower() in _VIDEO_EXTS
```

Then in `build_inventory`, replace the non-album construction loop so videos go to a separate list:

```python
    # Non-album media = post media whose fbid is not in any album file (dedup by fbid).
    # Videos are split off into their own category (auto-kept, thumbnail-replaced).
    non_album: list[Photo] = []
    videos: list[Photo] = []
    seen: set[str] = set()
    for r in post_records:
        fbid = photo_fbid(r["uri"])
        if fbid in album_fbids or fbid in seen:
            continue
        seen.add(fbid)
        resolved = resolve_uri(r["uri"], export_root)
        ts = r.get("creation_timestamp")
        photo = Photo(
            fbid=fbid,
            original_uri=r["uri"],
            resolved_path=resolved,
            title=r["title"],
            caption=r["caption"] or None,
            creation_at=epoch_to_dt(ts) if ts else None,
            album_fbid=None,
            exists=resolved.exists(),
            is_video=is_video_uri(r["uri"]),
        )
        (videos if photo.is_video else non_album).append(photo)

    inventory = ExportInventory(albums=albums, non_album_photos=non_album, videos=videos)
    partition_archive(inventory)
    derive_caption_albums(inventory)
    return inventory
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/inventory/test_video_parser.py tests/inventory -q`
Expected: PASS (and no regressions in existing inventory tests).

- [ ] **Step 7: Commit**

```bash
git add src/streamlinify/inventory/models.py src/streamlinify/inventory/parser.py tests/conftest.py tests/inventory/test_video_parser.py
git commit -m "feat(inventory): split videos into their own category"
```

---

## Task 2: Video thumbnail store + session wiring

**Files:**
- Create: `src/streamlinify/thumbnails/video_store.py`
- Modify: `src/streamlinify/web/session.py`
- Modify: `src/streamlinify/web/routes_ingest.py:45-60` (`_start_session`)
- Test: `tests/thumbnails/test_video_store.py`

**Interfaces:**
- Produces: `VideoThumbnailStore(base_dir: Path)` with `.dir: Path`, `.path(fbid) -> Path`, `.has(fbid) -> bool`, `.save(fbid, data: bytes) -> Path`; `Session.video_thumbs: VideoThumbnailStore`.

- [ ] **Step 1: Write the failing test**

Create `tests/thumbnails/test_video_store.py`:

```python
from pathlib import Path

from streamlinify.thumbnails.video_store import VideoThumbnailStore


def test_save_and_read(tmp_path: Path):
    store = VideoThumbnailStore(tmp_path / "videos")
    assert not store.has("v01")
    p = store.save("v01", b"JPEGBYTES")
    assert p == tmp_path / "videos" / "v01.jpg"
    assert store.has("v01")
    assert p.read_bytes() == b"JPEGBYTES"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/thumbnails/test_video_store.py -q`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement the store**

Create `src/streamlinify/thumbnails/video_store.py`:

```python
from __future__ import annotations

from pathlib import Path


class VideoThumbnailStore:
    """On-disk store for per-video still frames chosen in the browser.

    One file per video: <base_dir>/<fbid>.jpg. Lives under workspace/ (gitignored),
    never in the read-only export. The frame itself is captured client-side.
    """

    def __init__(self, base_dir: Path) -> None:
        self.dir = base_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def path(self, fbid: str) -> Path:
        return self.dir / f"{fbid}.jpg"

    def has(self, fbid: str) -> bool:
        return self.path(fbid).exists()

    def save(self, fbid: str, data: bytes) -> Path:
        target = self.path(fbid)
        target.write_bytes(data)
        return target
```

- [ ] **Step 4: Wire it into the session**

In `src/streamlinify/web/session.py`, add the field and import:

```python
from ..thumbnails.service import ThumbnailService
from ..thumbnails.video_store import VideoThumbnailStore


@dataclass
class Session:
    export_root: Path
    inventory: ExportInventory
    selection: SelectionState
    thumbnails: ThumbnailService
    video_thumbs: VideoThumbnailStore
```

In `src/streamlinify/web/routes_ingest.py`, import the store and construct it in `_start_session`:

```python
from ..thumbnails.video_store import VideoThumbnailStore
```

```python
    request.app.state.session = Session(
        export_root=export_root,
        inventory=inventory,
        selection=SelectionState(
            workspace / "selection.json", DefaultPolicy(uncapped_albums=uncapped)
        ),
        thumbnails=ThumbnailService(workspace / "thumbs"),
        video_thumbs=VideoThumbnailStore(workspace / "thumbs" / "videos"),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/thumbnails -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/streamlinify/thumbnails/video_store.py src/streamlinify/web/session.py src/streamlinify/web/routes_ingest.py tests/thumbnails/test_video_store.py
git commit -m "feat(thumbnails): add per-video still store on the session"
```

---

## Task 3: Video routes (stream / save still / get still)

**Files:**
- Create: `src/streamlinify/web/routes_video.py`
- Modify: `src/streamlinify/app.py:20-26` (register router)
- Test: `tests/web/test_video_routes.py`

**Interfaces:**
- Consumes: `Session.inventory.videos`, `Session.video_thumbs`.
- Produces: `GET /api/video/{fbid}`, `GET /api/video/{fbid}/thumbnail`, `POST /api/video/{fbid}/thumbnail`.

- [ ] **Step 1: Write the failing test**

Create `tests/web/test_video_routes.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from streamlinify.app import create_app


def _loaded_client(export_root: Path, tmp_path, monkeypatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    client.post("/api/ingest/folder", json={"folder": str(export_root)})
    return client


def test_video_stream_served(video_export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(video_export_root, tmp_path, monkeypatch)
    resp = client.get("/api/video/v01")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("video/")
    assert resp.content.startswith(b"\x00\x00\x00\x18ftyp")


def test_video_stream_supports_range(video_export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(video_export_root, tmp_path, monkeypatch)
    resp = client.get("/api/video/v01", headers={"Range": "bytes=0-3"})
    assert resp.status_code == 206
    assert len(resp.content) == 4


def test_video_stream_unknown_404(video_export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(video_export_root, tmp_path, monkeypatch)
    assert client.get("/api/video/nope").status_code == 404


def test_thumbnail_missing_then_saved(video_export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(video_export_root, tmp_path, monkeypatch)
    assert client.get("/api/video/v01/thumbnail").status_code == 404
    save = client.post("/api/video/v01/thumbnail", content=b"JPEGBYTES",
                       headers={"content-type": "image/jpeg"})
    assert save.status_code == 200 and save.json() == {"ok": True}
    got = client.get("/api/video/v01/thumbnail")
    assert got.status_code == 200 and got.content == b"JPEGBYTES"


def test_save_thumbnail_unknown_video_404(video_export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(video_export_root, tmp_path, monkeypatch)
    assert client.post("/api/video/nope/thumbnail", content=b"X").status_code == 404


def test_video_route_cors_header(video_export_root: Path, tmp_path: Path, monkeypatch):
    client = _loaded_client(video_export_root, tmp_path, monkeypatch)
    resp = client.get("/api/video/v01", headers={"Origin": "http://localhost:5173"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/web/test_video_routes.py -q`
Expected: FAIL (404 on all — routes not registered).

- [ ] **Step 3: Implement the router**

Create `src/streamlinify/web/routes_video.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter()


def _session(request: Request):
    session = request.app.state.session
    if session is None:
        raise HTTPException(status_code=404, detail="No export loaded")
    return session


def _video(session, fbid: str):
    video = next((v for v in session.inventory.videos if v.fbid == fbid), None)
    if video is None:
        raise HTTPException(status_code=404, detail="No such video")
    return video


@router.get("/api/video/{fbid}")
def video_file(request: Request, fbid: str):
    """Stream the raw mp4 for in-browser playback. FileResponse honors Range
    requests, so the scrubber can seek. Read-only original; never modified."""
    session = _session(request)
    video = _video(session, fbid)
    if not video.resolved_path.exists():
        raise HTTPException(status_code=404, detail="Video file missing")
    return FileResponse(video.resolved_path, media_type="video/mp4")


@router.get("/api/video/{fbid}/thumbnail")
def get_video_thumbnail(request: Request, fbid: str):
    session = _session(request)
    _video(session, fbid)
    path = session.video_thumbs.path(fbid)
    if not path.exists():
        raise HTTPException(status_code=404, detail="No thumbnail chosen yet")
    return FileResponse(path, media_type="image/jpeg")


@router.post("/api/video/{fbid}/thumbnail")
async def save_video_thumbnail(request: Request, fbid: str):
    """Store a frame captured client-side (raw JPEG bytes in the request body)."""
    session = _session(request)
    _video(session, fbid)
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="Empty thumbnail body")
    session.video_thumbs.save(fbid, data)
    return {"ok": True}
```

- [ ] **Step 4: Register the router**

In `src/streamlinify/app.py`, add the import and include it after the gallery router:

```python
    from .web.routes_build import router as build_router
    from .web.routes_gallery import router as gallery_router
    from .web.routes_ingest import router as ingest_router
    from .web.routes_video import router as video_router

    app.include_router(ingest_router)
    app.include_router(gallery_router)
    app.include_router(video_router)
    app.include_router(build_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/web/test_video_routes.py -q`
Expected: PASS (all six).

- [ ] **Step 6: Commit**

```bash
git add src/streamlinify/web/routes_video.py src/streamlinify/app.py tests/web/test_video_routes.py
git commit -m "feat(web): stream videos and store chosen stills"
```

---

## Task 4: Serializer `videos` array

**Files:**
- Modify: `src/streamlinify/web/serializers.py`
- Test: `tests/web/test_serializers.py`

**Interfaces:**
- Produces: `inventory_payload(...)["videos"]` = list of `{fbid, caption, exists}` (no `selected`).

- [ ] **Step 1: Write the failing test**

Add to `tests/web/test_serializers.py` (match the file's existing import/fixture style; it builds an inventory via `build_inventory`):

```python
def test_payload_includes_videos(video_export_root):
    from streamlinify.inventory.parser import build_inventory
    from streamlinify.selection.state import SelectionState
    from streamlinify.selection.policy import DefaultPolicy
    from streamlinify.web.serializers import inventory_payload

    inv = build_inventory(video_export_root)
    sel = SelectionState(video_export_root / "sel.json", DefaultPolicy())
    payload = inventory_payload("video_export", inv, sel, 10)

    assert [v["fbid"] for v in payload["videos"]] == ["v01"]
    assert payload["videos"][0]["caption"] == "Watch this clip #ARCH"
    assert "selected" not in payload["videos"][0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/web/test_serializers.py::test_payload_includes_videos -q`
Expected: FAIL (`KeyError: 'videos'`).

- [ ] **Step 3: Add the videos array**

In `src/streamlinify/web/serializers.py`, add `videos` to the returned dict:

```python
    return {
        "export_name": export_name,
        "max_per_album": max_per_album,
        "albums": albums,
        "non_album": [_photo(p) for p in inventory.non_album_photos],
        "videos": [_photo(v) for v in inventory.videos],
        "archive": [_archive_photo(p) for p in inventory.archived_photos],
    }
```

(`_photo` with no `selected` argument already omits the `selected` key — exactly what videos need.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/web/test_serializers.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/streamlinify/web/serializers.py tests/web/test_serializers.py
git commit -m "feat(web): expose videos in the inventory payload"
```

---

## Task 5: Builder — stills replace videos; feed URIs rewritten; skips reported

**Files:**
- Modify: `src/streamlinify/transform/builder.py`
- Modify: `src/streamlinify/transform/report.py`
- Modify: `src/streamlinify/web/routes_build.py`
- Test: `tests/transform/test_video_build.py`

**Interfaces:**
- Consumes: `Session.video_thumbs.dir`.
- Produces: `build_ready_folder(export_root, dest, keep_fbids, video_thumb_dir: Path | None = None) -> BuildResult`; `BuildResult.videos_built: int`; `BuildResult.skipped_videos: list[str]`.

- [ ] **Step 1: Write the failing test**

Create `tests/transform/test_video_build.py`:

```python
import json
from pathlib import Path

from streamlinify.transform.builder import build_ready_folder


def test_video_still_replaces_mp4(video_export_root: Path, tmp_path: Path):
    thumbs = tmp_path / "vthumbs"
    thumbs.mkdir()
    (thumbs / "v01.jpg").write_bytes(b"CHOSENFRAME")

    dest = tmp_path / "ready"
    result = build_ready_folder(video_export_root, dest, keep_fbids=set(), video_thumb_dir=thumbs)

    # the .jpg is written in the video's slot; the .mp4 is NOT copied
    assert (dest / "posts" / "media" / "videos" / "v01.jpg").read_bytes() == b"CHOSENFRAME"
    assert not (dest / "posts" / "media" / "videos" / "v01.mp4").exists()
    assert result.videos_built == 1 and result.skipped_videos == []

    # the rebuilt feed references the .jpg, not the .mp4
    posts = json.loads((dest / "posts" / "profile_posts_1.json").read_text(encoding="utf-8"))
    uris = [d["media"]["uri"] for p in posts for att in p["attachments"] for d in att["data"] if "media" in d]
    assert any(u.endswith("videos/v01.jpg") for u in uris)
    assert not any(u.endswith(".mp4") for u in uris)


def test_video_without_still_is_skipped(video_export_root: Path, tmp_path: Path):
    dest = tmp_path / "ready"
    result = build_ready_folder(video_export_root, dest, keep_fbids=set(), video_thumb_dir=tmp_path / "empty")

    assert result.videos_built == 0
    assert any("v01.mp4" in s for s in result.skipped_videos)
    assert not (dest / "posts" / "media" / "videos" / "v01.jpg").exists()
    assert not (dest / "posts" / "media" / "videos" / "v01.mp4").exists()
    # the skipped video is dropped from the feed
    posts = json.loads((dest / "posts" / "profile_posts_1.json").read_text(encoding="utf-8"))
    uris = [d["media"]["uri"] for p in posts for att in p["attachments"] for d in att["data"] if "media" in d]
    assert not any("v01" in u for u in uris)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/transform/test_video_build.py -q`
Expected: FAIL (`build_ready_folder() got an unexpected keyword argument 'video_thumb_dir'`).

- [ ] **Step 3: Extend `BuildResult` and the builder**

In `src/streamlinify/transform/builder.py`, update imports and the dataclass:

```python
from dataclasses import dataclass, field
```

```python
@dataclass
class BuildResult:
    ready_root: Path
    copied: int
    albums_written: int
    orphans: list[str]
    videos_built: int = 0
    skipped_videos: list[str] = field(default_factory=list)
```

Change the signature:

```python
def build_ready_folder(
    export_root: Path, dest: Path, keep_fbids: set[str], video_thumb_dir: Path | None = None
) -> BuildResult:
```

Immediately **after** the `present_fbids = {...}` block (and before `album_dst_dir = ...`), insert the video handling:

```python
    # Videos: never copy the .mp4. Copy the chosen still into the video's slot as a
    # .jpg and remember the rewritten uri so the feed points at the image. A video
    # with no chosen still is skipped and reported (the .mp4 is never a fallback).
    video_ready: dict[str, str] = {}
    skipped_videos: list[str] = []
    videos_built = 0
    for video in inventory.videos:
        still = (video_thumb_dir / f"{video.fbid}.jpg") if video_thumb_dir else None
        if still is None or not still.exists():
            skipped_videos.append(video.original_uri)
            continue
        rel = _rel_from_posts(video.original_uri).rsplit(".", 1)[0] + ".jpg"
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(still, target)
        video_ready[video.fbid] = rel
        videos_built += 1
```

In the `profile_posts` rewrite loop, handle videos first inside the `for d in att.get("data", [])` block:

```python
                for d in att.get("data", []):
                    if "media" not in d:
                        continue
                    fbid = photo_fbid(d["media"]["uri"])
                    if fbid in video_ready:
                        d["media"]["uri"] = video_ready[fbid]
                        kept_data.append(d)
                        continue
                    if fbid not in present_fbids:
                        continue
                    if fbid in ready_uris:
                        d["media"]["uri"] = ready_uris[fbid]
                    kept_data.append(d)
```

Update the final return:

```python
    return BuildResult(
        ready_root=dest,
        copied=copied,
        albums_written=albums_written,
        orphans=orphans,
        videos_built=videos_built,
        skipped_videos=skipped_videos,
    )
```

- [ ] **Step 4: Surface videos in the report**

In `src/streamlinify/transform/report.py`, extend `format_summary`:

```python
def format_summary(result: BuildResult) -> str:
    lines = [
        f"Ready folder: {result.ready_root}",
        f"Media files copied: {result.copied}",
        f"Video stills written: {result.videos_built}",
        f"Albums written: {result.albums_written}",
        f"Orphans (referenced but missing on disk): {len(result.orphans)}",
    ]
    lines.extend(f"  - {o}" for o in result.orphans)
    if result.skipped_videos:
        lines.append(f"Videos skipped (no thumbnail chosen): {len(result.skipped_videos)}")
        lines.extend(f"  - {s}" for s in result.skipped_videos)
    return "\n".join(lines)
```

- [ ] **Step 5: Pass the store dir and counts through the build route**

In `src/streamlinify/web/routes_build.py`, pass the dir and add counts to the response:

```python
    result = build_ready_folder(
        session.export_root, dest, keep, session.video_thumbs.dir
    )
```

```python
    return {
        "copied": result.copied,
        "videos_built": result.videos_built,
        "skipped_videos": result.skipped_videos,
        "albums_written": result.albums_written,
        "orphans": result.orphans,
        "summary": format_summary(result),
    }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `UV_LINK_MODE=copy uv run --no-sync pytest tests/transform tests/web/test_build_route.py -q`
Expected: PASS (video build tests + no regression in the existing build tests).

- [ ] **Step 7: Commit**

```bash
git add src/streamlinify/transform/builder.py src/streamlinify/transform/report.py src/streamlinify/web/routes_build.py tests/transform/test_video_build.py
git commit -m "feat(transform): replace videos with chosen stills in the build"
```

---

## Task 6: Frontend API helpers + canvas capture util

**Files:**
- Modify: `frontend/src/lib/api.js`
- Create: `frontend/src/lib/videoThumbs.js`
- Test: `frontend/src/lib/api.test.js` (add), `frontend/src/lib/videoThumbs.test.js` (new)

**Interfaces:**
- Produces: `videoUrl(fbid)`, `videoThumbUrl(fbid)`, `saveVideoThumbnail(fbid, blob, fetchFn?)`, `captureFrame(videoEl, quality?) -> Promise<Blob>`, `seedThumbnail(fbid, videoSrc)`, `seedMissingThumbnails(videos, {videoSrc, needsSeed, onSeeded})`.

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/lib/api.test.js`:

```js
import { videoUrl, videoThumbUrl, saveVideoThumbnail } from './api.js';

describe('video api', () => {
	it('builds video + thumbnail urls', () => {
		expect(videoUrl('v01')).toMatch(/\/api\/video\/v01$/);
		expect(videoThumbUrl('v01')).toMatch(/\/api\/video\/v01\/thumbnail$/);
	});

	it('POSTs the captured blob as image/jpeg', async () => {
		const fetchFn = vi.fn().mockResolvedValue({ ok: true });
		const blob = new Blob(['x'], { type: 'image/jpeg' });
		const res = await saveVideoThumbnail('v01', blob, fetchFn);
		expect(res).toEqual({ ok: true });
		const [, opts] = fetchFn.mock.calls[0];
		expect(opts.method).toBe('POST');
		expect(opts.headers['content-type']).toBe('image/jpeg');
		expect(opts.body).toBe(blob);
	});
});
```

Create `frontend/src/lib/videoThumbs.test.js`:

```js
import { describe, expect, it, vi } from 'vitest';
import { captureFrame } from './videoThumbs.js';

describe('captureFrame', () => {
	it('draws the video and resolves the canvas blob', async () => {
		const blob = new Blob(['frame'], { type: 'image/jpeg' });
		const ctx = { drawImage: vi.fn() };
		const canvas = {
			width: 0,
			height: 0,
			getContext: () => ctx,
			toBlob: (cb) => cb(blob)
		};
		vi.spyOn(document, 'createElement').mockReturnValue(canvas);
		const video = { videoWidth: 320, videoHeight: 240 };

		const out = await captureFrame(video);
		expect(out).toBe(blob);
		expect(canvas.width).toBe(320);
		expect(canvas.height).toBe(240);
		expect(ctx.drawImage).toHaveBeenCalledWith(video, 0, 0, 320, 240);
	});
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm run test -- src/lib/videoThumbs.test.js src/lib/api.test.js`
Expected: FAIL (module `videoThumbs.js` missing; `videoUrl` undefined).

- [ ] **Step 3: Add the API helpers**

Append to `frontend/src/lib/api.js` (before the final `export { API_BASE };`):

```js
export function videoUrl(fbid) {
	return url(`/api/video/${encodeURIComponent(fbid)}`);
}

export function videoThumbUrl(fbid) {
	return url(`/api/video/${encodeURIComponent(fbid)}/thumbnail`);
}

/** POST a captured frame (Blob) as the chosen still for a video. */
export async function saveVideoThumbnail(fbid, blob, fetchFn = fetch) {
	const res = await fetchFn(url(`/api/video/${encodeURIComponent(fbid)}/thumbnail`), {
		method: 'POST',
		headers: { 'content-type': 'image/jpeg' },
		body: blob
	});
	return { ok: res.ok };
}
```

- [ ] **Step 4: Implement the capture util**

Create `frontend/src/lib/videoThumbs.js`:

```js
import { saveVideoThumbnail, videoThumbUrl } from './api.js';

/**
 * Draw a <video>'s current frame to a JPEG Blob. The <video> MUST be loaded with
 * crossorigin="anonymous" from a CORS-enabled source, or the canvas is tainted and
 * toBlob throws a SecurityError.
 */
export function captureFrame(videoEl, quality = 0.85) {
	const canvas = document.createElement('canvas');
	canvas.width = videoEl.videoWidth;
	canvas.height = videoEl.videoHeight;
	canvas.getContext('2d').drawImage(videoEl, 0, 0, canvas.width, canvas.height);
	return new Promise((resolve, reject) => {
		canvas.toBlob(
			(b) => (b ? resolve(b) : reject(new Error('capture produced no blob'))),
			'image/jpeg',
			quality
		);
	});
}

/** Load a video off-screen, seek ~0.1s, capture, and save as its default still. */
export async function seedThumbnail(fbid, videoSrc) {
	const v = document.createElement('video');
	v.crossOrigin = 'anonymous';
	v.muted = true;
	v.preload = 'auto';
	v.src = videoSrc;
	await new Promise((res, rej) => {
		v.addEventListener('loadeddata', res, { once: true });
		v.addEventListener('error', () => rej(new Error('video load failed')), { once: true });
	});
	await new Promise((res) => {
		v.addEventListener('seeked', res, { once: true });
		v.currentTime = Math.min(0.1, (v.duration || 1) / 2);
	});
	const blob = await captureFrame(v);
	v.removeAttribute('src');
	v.load();
	return saveVideoThumbnail(fbid, blob);
}

/**
 * Seed default stills for videos that don't have one yet, one at a time so we don't
 * pull every mp4 at once. `needsSeed(fbid) -> Promise<bool>`, `videoSrc(fbid) -> url`.
 */
export async function seedMissingThumbnails(videos, { videoSrc, needsSeed, onSeeded }) {
	for (const v of videos) {
		try {
			if (!(await needsSeed(v.fbid))) continue;
			await seedThumbnail(v.fbid, videoSrc(v.fbid));
			onSeeded?.(v.fbid);
		} catch {
			/* leave the placeholder; the build reports videos with no still */
		}
	}
}

/** Default `needsSeed`: a video needs a default when GET thumbnail is not 200. */
export function thumbnailMissing(fbid, fetchFn = fetch) {
	return fetchFn(videoThumbUrl(fbid), { method: 'GET' }).then((r) => !r.ok).catch(() => true);
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm run test -- src/lib/videoThumbs.test.js src/lib/api.test.js`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api.js frontend/src/lib/videoThumbs.js frontend/src/lib/api.test.js frontend/src/lib/videoThumbs.test.js
git commit -m "feat(frontend): video api helpers and canvas frame capture"
```

---

## Task 7: Video tile mode (play badge, no checkmark, click opens preview)

**Files:**
- Modify: `frontend/src/lib/components/PhotoTile.svelte`
- Modify: `frontend/src/lib/components/PhotoGrid.svelte`
- Test: `frontend/src/lib/components/PhotoTile.test.js` (add)

**Interfaces:**
- Produces: `PhotoTile` and `PhotoGrid` accept `video = false`. In video mode: the tile is interactive when `photo.exists`, shows a play badge, hides all selection UI, and calls `onToggle(photo)` on click. `PhotoGrid` forwards `video` to each tile.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/lib/components/PhotoTile.test.js`:

```js
it('renders a video tile with a play badge, no checkmark, and opens on click', async () => {
	const onToggle = vi.fn();
	render(PhotoTile, {
		props: {
			photo: { fbid: 'v01', exists: true, caption: 'clip' },
			src: '/api/video/v01/thumbnail',
			video: true,
			selectable: false,
			onToggle
		}
	});
	const tile = screen.getByTestId('tile-v01');
	expect(tile).not.toBeDisabled();
	expect(screen.getByTestId('video-badge-v01')).toBeInTheDocument();
	await fireEvent.click(tile);
	expect(onToggle).toHaveBeenCalledOnce();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- src/lib/components/PhotoTile.test.js`
Expected: FAIL (no `video-badge-v01`).

- [ ] **Step 3: Add video mode to `PhotoTile`**

In `frontend/src/lib/components/PhotoTile.svelte`, update the props line and derived state:

```js
	let { photo, src = '', selectable = true, full = false, video = false, onToggle } = $props();

	// A tile the user can't act on right now: the album is full and this one
	// isn't already selected. Selected tiles stay clickable so they can be removed.
	let blocked = $derived(!video && full && !photo.selected);
	let interactive = $derived(video ? photo.exists : selectable && photo.exists && !blocked);
	let imgError = $state(false);
```

Replace the `<img>` element so a 404 thumbnail falls back to a placeholder:

```svelte
		{#if !imgError}
			<img
				class="size-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
				loading="lazy"
				onload={measure}
				onerror={() => (imgError = true)}
				{src}
				alt={photo.caption || photo.fbid}
			/>
		{:else}
			<span class="grid size-full place-items-center bg-surface-200 text-surface-400">
				<svg viewBox="0 0 24 24" class="size-8" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>
			</span>
		{/if}
```

Wrap the existing selection cluster (the `{#if photo.selected} … {:else if interactive} … {:else if blocked} …` block) so it only renders for non-videos, and add the play badge for videos. Change the opening of that block to:

```svelte
			{#if video}
				<span
					data-testid={`video-badge-${photo.fbid}`}
					class="pointer-events-none absolute inset-0 grid place-items-center"
					aria-hidden="true"
				>
					<span class="grid size-11 place-items-center rounded-full bg-surface-950/55 text-surface-50 shadow-lg transition-transform group-hover:scale-110">
						<svg viewBox="0 0 24 24" class="size-6" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
					</span>
				</span>
			{:else if photo.selected}
```

(The rest of that `{:else if interactive}` / `{:else if blocked}` chain stays as-is — it now only applies to non-videos.)

- [ ] **Step 4: Forward `video` through `PhotoGrid`**

In `frontend/src/lib/components/PhotoGrid.svelte`, add `video = false` to props and pass it down:

```svelte
	let { album, thumb, full = false, size = 'm', selectable = true, video = false, onToggle, onContextMenu } = $props();
```

```svelte
		<PhotoTile {photo} src={photo.exists ? thumb(photo.fbid) : ''} {full} {selectable} {video} {onToggle} />
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm run test -- src/lib/components/PhotoTile.test.js`
Expected: PASS (new test + existing three).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/components/PhotoTile.svelte frontend/src/lib/components/PhotoGrid.svelte frontend/src/lib/components/PhotoTile.test.js
git commit -m "feat(frontend): video tile mode with play badge"
```

---

## Task 8: `VideoPreview` picker component

**Files:**
- Create: `frontend/src/lib/components/VideoPreview.svelte`
- Test: `frontend/src/lib/components/VideoPreview.test.js`

**Interfaces:**
- Consumes: `videoUrl`, `videoThumbUrl`, `saveVideoThumbnail` (api.js), `captureFrame` (videoThumbs.js).
- Produces: `VideoPreview` props `{ video, onClose, onThumbnailChosen }`. Renders `<video crossorigin controls>` on the left and the current still on the right (vertically centered, 30% smaller). "Choose Thumbnail" captures the current frame, saves it, and calls `onThumbnailChosen(fbid)`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/components/VideoPreview.test.js`:

```js
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

vi.mock('$lib/videoThumbs.js', () => ({
	captureFrame: vi.fn().mockResolvedValue(new Blob(['f'], { type: 'image/jpeg' }))
}));
vi.mock('$lib/api.js', () => ({
	videoUrl: (id) => `/api/video/${id}`,
	videoThumbUrl: (id) => `/api/video/${id}/thumbnail`,
	saveVideoThumbnail: vi.fn().mockResolvedValue({ ok: true })
}));

import { captureFrame, saveVideoThumbnail } from '$lib/api.js';
import VideoPreview from './VideoPreview.svelte';

describe('VideoPreview', () => {
	it('captures and saves the current frame, then notifies', async () => {
		const onThumbnailChosen = vi.fn();
		render(VideoPreview, {
			props: { video: { fbid: 'v01', caption: 'clip' }, onClose: vi.fn(), onThumbnailChosen }
		});
		await fireEvent.click(screen.getByRole('button', { name: /choose thumbnail/i }));
		const { captureFrame: cap } = await import('$lib/videoThumbs.js');
		expect(cap).toHaveBeenCalledOnce();
		expect(saveVideoThumbnail).toHaveBeenCalledWith('v01', expect.any(Blob));
		expect(onThumbnailChosen).toHaveBeenCalledWith('v01');
	});
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- src/lib/components/VideoPreview.test.js`
Expected: FAIL (component missing).

- [ ] **Step 3: Implement `VideoPreview`**

Create `frontend/src/lib/components/VideoPreview.svelte`:

```svelte
<script>
	import { onMount, onDestroy } from 'svelte';
	import { videoUrl, videoThumbUrl, saveVideoThumbnail } from '$lib/api.js';
	import { captureFrame } from '$lib/videoThumbs.js';

	let { video, onClose, onThumbnailChosen } = $props();

	let videoEl = $state();
	let videoH = $state(0);
	let videoW = $state(0);
	let closeBtn = $state();
	let saving = $state(false);
	// Bust the <img> cache after we save a new still so the panel updates.
	let stillVersion = $state(0);
	let stillSrc = $derived(`${videoThumbUrl(video.fbid)}?v=${stillVersion}`);
	let hasStill = $state(true); // assume a default exists; onerror flips it off

	async function choose() {
		if (!videoEl || saving) return;
		saving = true;
		try {
			const blob = await captureFrame(videoEl);
			await saveVideoThumbnail(video.fbid, blob);
			stillVersion += 1;
			hasStill = true;
			onThumbnailChosen?.(video.fbid);
		} finally {
			saving = false;
		}
	}

	function onKey(e) {
		if (e.key === 'Escape') {
			e.preventDefault();
			onClose();
		}
	}

	let opener;
	onMount(() => {
		opener = document.activeElement;
		document.body.style.overflow = 'hidden';
		closeBtn?.focus();
	});
	onDestroy(() => {
		document.body.style.overflow = '';
		opener?.focus?.();
	});
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div
	class="fixed inset-0 z-[60] flex flex-col bg-surface-950/80 backdrop-blur-sm"
	role="dialog"
	aria-modal="true"
	aria-label="Video thumbnail picker"
	tabindex="-1"
	onkeydown={onKey}
>
	<div class="flex items-center gap-3 px-4 py-3 text-surface-50 sm:px-6">
		<div class="min-w-0">
			<p class="truncate text-sm font-medium" title={video.caption || video.fbid}>
				{video.caption || video.fbid}
			</p>
			<p class="text-xs text-surface-300">Play, then choose the frame to keep · this video is always kept</p>
		</div>
		<div class="ml-auto flex items-center gap-2">
			<button
				type="button"
				class="flex h-9 items-center gap-1.5 rounded-lg bg-primary-600 px-3 text-sm font-semibold text-primary-50 shadow-sm transition-colors hover:bg-primary-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-300 disabled:opacity-70"
				onclick={choose}
				disabled={saving}
			>
				<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2"
					stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="9" cy="9" r="2" /><path d="m21 15-5-5L5 21" /></svg>
				{saving ? 'Saving…' : 'Choose Thumbnail'}
			</button>
			<button
				bind:this={closeBtn}
				type="button"
				class="grid size-9 place-items-center rounded-lg text-surface-100 transition-colors hover:bg-surface-50/15 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-300"
				onclick={onClose}
				aria-label="Close preview"
			>
				<svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="2"
					stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12" /></svg>
			</button>
		</div>
	</div>

	<!-- Stage: video left, chosen still right (vertically centred, 30% smaller). -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="relative flex min-h-0 flex-1 items-center justify-center gap-6 px-4 sm:px-12"
		onclick={(e) => e.target === e.currentTarget && onClose()}
	>
		<!-- svelte-ignore a11y_media_has_caption -->
		<video
			bind:this={videoEl}
			bind:clientHeight={videoH}
			bind:clientWidth={videoW}
			class="max-h-full max-w-[70%] rounded-lg shadow-2xl"
			crossorigin="anonymous"
			controls
			src={videoUrl(video.fbid)}
		></video>

		<div class="flex items-center" style="height: {videoH}px;">
			{#if hasStill}
				<figure class="flex flex-col items-center gap-2">
					<img
						class="rounded-lg object-contain shadow-xl ring-1 ring-surface-50/20"
						style="max-height: {videoH * 0.7}px; max-width: {videoW * 0.7}px;"
						src={stillSrc}
						alt="Chosen thumbnail"
						onerror={() => (hasStill = false)}
					/>
					<figcaption class="text-xs text-surface-300">Chosen thumbnail</figcaption>
				</figure>
			{:else}
				<p class="max-w-[10rem] text-center text-xs text-surface-400">
					No thumbnail yet — play to a frame and click “Choose Thumbnail”.
				</p>
			{/if}
		</div>
	</div>

	<p class="px-4 pb-3 pt-1 text-center text-xs text-surface-400">
		<kbd class="font-sans">Esc</kbd> to close
	</p>
</div>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm run test -- src/lib/components/VideoPreview.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/components/VideoPreview.svelte frontend/src/lib/components/VideoPreview.test.js
git commit -m "feat(frontend): VideoPreview thumbnail picker"
```

---

## Task 9: Wire Videos into the gallery (category, grid, context menu, auto-seed)

**Files:**
- Modify: `frontend/src/lib/components/AlbumList.svelte`
- Modify: `frontend/src/routes/gallery/+page.svelte`
- Test: `frontend/src/lib/components/AlbumList.test.js` (add)

**Interfaces:**
- Consumes: `inventory.videos`, `videoThumbUrl`, `seedMissingThumbnails`, `thumbnailMissing`, `VideoPreview`.
- Produces: a "Videos" left-rail entry (`activeId === '__videos__'`), a non-selectable video grid whose tiles open `VideoPreview`, a video context menu with "Choose Thumbnail", and background default-seeding on mount.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/lib/components/AlbumList.test.js` (follow the file's existing render/prop style):

```js
it('shows a Videos entry and selects it', async () => {
	const onSelect = vi.fn();
	render(AlbumList, {
		props: { albums: [], nonAlbumCount: 0, videosCount: 3, activeId: null, onSelect, onContextMenu: vi.fn() }
	});
	const btn = screen.getByRole('button', { name: /videos/i });
	expect(btn).toBeInTheDocument();
	await fireEvent.click(btn);
	expect(onSelect).toHaveBeenCalledWith('__videos__');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- src/lib/components/AlbumList.test.js`
Expected: FAIL (no Videos entry).

- [ ] **Step 3: Add the Videos entry to `AlbumList`**

In `frontend/src/lib/components/AlbumList.svelte`, add `videosCount = 0` to props:

```js
	let { albums, nonAlbumCount, archiveCount = 0, videosCount = 0, activeId, onSelect, onContextMenu } = $props();
```

Insert a Videos button immediately **before** the `{#if archiveCount > 0}` block:

```svelte
	{#if videosCount > 0}
		{@const active = activeId === '__videos__'}
		<div class="my-1 h-px bg-surface-300"></div>
		<button
			type="button"
			class="flex items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
			class:bg-primary-100={active}
			class:text-primary-900={active}
			class:font-semibold={active}
			class:text-surface-700={!active}
			class:hover:bg-surface-200={!active}
			onclick={() => onSelect('__videos__')}
			aria-current={active ? 'true' : undefined}
			title="Videos are always kept — pick a still frame to represent each one."
		>
			<svg viewBox="0 0 24 24" class="size-4 shrink-0" fill="none" stroke="currentColor"
				stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="5" width="14" height="14" rx="2" /><path d="m16 10 6-3v10l-6-3z" /></svg>
			<span class="truncate">Videos</span>
			<span class="ml-auto shrink-0 rounded-full bg-surface-200 px-2 py-0.5 text-xs font-medium tabular-nums text-surface-600">{videosCount}</span>
		</button>
	{/if}
```

- [ ] **Step 4: Run the AlbumList test to verify it passes**

Run: `cd frontend && npm run test -- src/lib/components/AlbumList.test.js`
Expected: PASS.

- [ ] **Step 5: Wire the gallery page**

In `frontend/src/routes/gallery/+page.svelte`:

Add imports:

```js
	import { build, reveal, thumbUrl, previewUrl, toggle, videoThumbUrl, videoUrl } from '$lib/api.js';
	import { seedMissingThumbnails, thumbnailMissing } from '$lib/videoThumbs.js';
	import VideoPreview from '$lib/components/VideoPreview.svelte';
```

Add state and derived values (near the other `$state`/`$derived` declarations):

```js
	let videos = $derived(inventory.videos ?? []);
	let showVideos = $derived(activeId === '__videos__');
	let videoPreview = $state(null); // the video obj being picked, or null
	// Cache-bust key per video so a freshly-seeded/chosen still reloads in the grid.
	let thumbVersion = $state({});
	function videoTileSrc(fbid) {
		return `${videoThumbUrl(fbid)}?v=${thumbVersion[fbid] ?? 0}`;
	}
```

Seed default stills once on mount (add a new `$effect`):

```js
	// On load, give every video a default first-frame still so the grid shows real
	// frames and every video is build-ready. Sequential + throttled via the util.
	$effect(() => {
		if (!videos.length) return;
		seedMissingThumbnails(videos, {
			videoSrc: videoUrl,
			needsSeed: (fbid) => thumbnailMissing(fbid),
			onSeeded: (fbid) => (thumbVersion = { ...thumbVersion, [fbid]: Date.now() })
		});
	});
```

Add a video context menu and preview opener (near `openPhotoMenu`):

```js
	function openVideoPreview(video) {
		videoPreview = video;
	}

	function onVideoChosen(fbid) {
		thumbVersion = { ...thumbVersion, [fbid]: Date.now() };
	}

	// Right-click a video → choose its thumbnail (replaces "Preview") or open its file.
	function openVideoMenu(video, e) {
		menu = {
			open: true,
			x: e.clientX,
			y: e.clientY,
			items: [
				{ label: 'Choose Thumbnail', icon: 'preview', onSelect: () => openVideoPreview(video) },
				{
					label: 'Show in File Explorer',
					icon: 'folder',
					disabled: !video.exists,
					hint: video.exists ? undefined : 'missing',
					onSelect: () => revealOnDisk({ photoFbid: video.fbid })
				}
			]
		};
	}
```

Pass `videosCount` to `AlbumList`:

```svelte
			<AlbumList
				albums={inventory.albums}
				nonAlbumCount={inventory.non_album.length}
				archiveCount={archive.length}
				videosCount={videos.length}
				{activeId}
				onSelect={(id) => (activeId = id)}
				onContextMenu={openAlbumMenu}
			/>
```

Render the Videos grid. In the right-pane `{#if showArchive} … {:else if activeAlbum} … {:else}` chain, add a `showVideos` branch **before** `{:else if activeAlbum}`:

```svelte
			{:else if showVideos}
				<header class="mb-4 shrink-0 pt-1 pb-3">
					<div class="flex min-w-0 items-baseline gap-3">
						<h1 class="truncate text-xl font-semibold tracking-tight text-surface-900">Videos</h1>
						<p class="shrink-0 text-sm font-medium tabular-nums text-surface-500">
							{videos.length} · always kept
						</p>
					</div>
					<p class="mt-2 text-sm text-surface-500">
						Videos aren’t imported — a still frame replaces each one. Click a video to play it and
						choose the frame, or right-click for “Choose Thumbnail”. A first frame is picked by default.
					</p>
				</header>

				{#if videos.length}
					<div class="lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain">
						<PhotoGrid
							album={{ name: 'Videos', photos: videos }}
							thumb={videoTileSrc}
							size={gridSize}
							selectable={false}
							video
							onToggle={openVideoPreview}
							onContextMenu={openVideoMenu}
						/>
					</div>
				{/if}
```

Render the `VideoPreview` modal (near the `PhotoPreview` blocks):

```svelte
{#if videoPreview}
	<VideoPreview
		video={videoPreview}
		onThumbnailChosen={onVideoChosen}
		onClose={() => (videoPreview = null)}
	/>
{/if}
```

- [ ] **Step 6: Run the full frontend suite**

Run: `cd frontend && npm run test`
Expected: PASS (all suites).

- [ ] **Step 7: Manual verification (browser)**

Free the port, then run both servers and exercise the flow:

```bash
npx kill-port 8000 5173
```

Start the API (`UV_LINK_MODE=copy uv run streamlinify`) and UI (`cd frontend && npm run dev`), ingest the real export, then:
- The left rail shows a **Videos** entry with a count; open it.
- Tiles show a real first frame (after brief background seeding) with a play badge and **no checkmark**.
- **Single-click** a tile → the video plays in `VideoPreview`; the chosen still shows on the right, vertically centered and ~30% smaller.
- Play/scrub, click **Choose Thumbnail** → the right panel updates to the new frame; the grid tile updates on close.
- **Right-click** a tile → the menu shows **Choose Thumbnail** (not "Preview") + Show in File Explorer.
- Click **Build ready folder**; confirm `workspace/ready/<export>/posts/media/videos/<fbid>.jpg` exists, **no** `.mp4` under `posts/media/videos/`, and `profile_posts_1.json` references the `.jpg`. The build summary reports "Video stills written".

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/components/AlbumList.svelte frontend/src/lib/components/AlbumList.test.js frontend/src/routes/gallery/+page.svelte
git commit -m "feat(frontend): Videos gallery category with thumbnail picker"
```

---

## Self-Review

**Spec coverage:**
- No video imported / still replaces it in output → Task 5 (builder copies `.jpg`, never `.mp4`; feed URI rewritten).
- Videos auto-kept for build → Tasks 1 + 5 (videos are their own category, always built when a still exists; never gated by `selection.json`).
- Videos browsable, formatted like images → Tasks 4, 7, 9 (payload, tile mode, grid).
- Single-click → preview mode → Task 9 (`onToggle={openVideoPreview}`).
- No checkmark on videos → Task 7 (video badge replaces the selection cluster).
- Context menu "Preview" → "Choose Thumbnail" → Task 9 (`openVideoMenu`).
- Scrub by second, capture frame → Task 8 (`<video controls>` + Choose Thumbnail).
- Chosen still on the right, centered, 30% smaller → Task 8 (`videoH * 0.7` / `videoW * 0.7`, flex `items-center`).
- Auto first-frame default (locked decision) → Tasks 6 + 9 (`seedMissingThumbnails` on mount).
- No ffmpeg / client-side capture → Task 6 (`captureFrame`).
- CORS/canvas-taint constraint → Task 3 CORS test + `crossorigin="anonymous"` in Tasks 6/8.
- Build safeguard: skip + report videos with no still → Task 5 (`skipped_videos`, report line).

**Placeholder scan:** none — every step contains full code or an exact command.

**Type consistency:** `is_video`, `videos`, `video_thumbs`, `VideoThumbnailStore.path/has/save`, `build_ready_folder(..., video_thumb_dir)`, `BuildResult.videos_built/skipped_videos`, `videoUrl/videoThumbUrl/saveVideoThumbnail`, `captureFrame/seedMissingThumbnails/thumbnailMissing`, and the `video`/`videosCount`/`activeId === '__videos__'` frontend names are used identically across the tasks that define and consume them.
