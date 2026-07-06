# Video Thumbnail Curation — Design

**Date:** 2026-07-06
**Status:** Approved (pending spec review)

## Problem

The Facebook export contains videos (`posts/media/videos/*.mp4`) referenced from
`profile_posts_1.json`. Today the parser treats each video's `.mp4` as an ordinary
non-album "photo": it is silently auto-kept, its `.mp4` is copied verbatim into the
build, and its gallery thumbnail fails because PIL cannot open an mp4.

Downstream (S3 + Postgres) wants **images, not video files**. We want to:

1. **Never import the video file** — the `.mp4` must not be copied into the build.
2. **Replace each video with a still image** in its output location (same path, `.jpg`).
3. **Auto-keep every video** for the build (no manual selection, no checkmark).
4. Let the volunteer **watch the video in the browser and pick which frame** becomes
   that still image.

### Key fact discovered during design

The export ships **no thumbnails for videos**. `posts/media/videos/` holds only
`.mp4` files; neither `videos.json` (`videos_v2`, 21 entries) nor the video records
inside `profile_posts_1.json` carry a `thumbnail` URI. In the real export the 21
videos referenced by `profile_posts` are exactly the 21 in `videos.json`, all present
on disk (10 further orphan `.mp4`s exist on disk but are referenced by neither, so they
are out of scope). Because there is no pre-existing thumbnail, one must be **generated**.

We generate it **client-side** by drawing a frame of the playing `<video>` to a
`<canvas>` — so **no ffmpeg / video dependency** is added to the backend.

## Scope

- **In scope:** videos referenced by `profile_posts_1.json` (extension-detected).
- **Out of scope:** the 10 orphan `.mp4`s referenced by nothing (never surfaced,
  never built — same as any other unreferenced media). `videos.json` stays dropped.

## Decisions (locked)

- **Default frame:** *auto first-frame default*. On gallery mount, the client lazily
  (sequential, throttled) captures each video's frame at ~0.1s and saves it as the
  default thumbnail, so every video is always build-ready. The picker overrides it.
- **Scrub precision:** *scrubber only* — timeline scrubber + play/pause at second-level
  precision. No per-frame stepping.
- **Thumbnail production:** client-side `<canvas>` capture. No ffmpeg.
- **Single entry point:** single-click a video tile **and** the context-menu
  "Choose Thumbnail" item both open the same `VideoPreview` screen.

## Architecture

### Backend (`src/streamlinify/`)

**Inventory / parser (`inventory/`)**
- Add video detection by URI extension (`.mp4`, `.mov`, `.webm`).
- `ExportInventory` gains `videos: list[Photo]`. Videos are pulled **out of**
  `non_album_photos` into `videos`, so they are a distinct, browsable category rather
  than part of the invisible auto-kept bucket. They carry caption/title/timestamp from
  the post records exactly as non-album photos do today.
- `Photo` gains `is_video: bool = False` (set on video records). `all_photos()` includes
  videos so existing fbid lookups keep working.
- `photo_by_fbid` / `all_photos` continue to resolve videos by fbid.

**Thumbnail storage**
- Chosen/default frames are written to `workspace/thumbs/videos/<fbid>.jpg`
  (a new dir next to the existing thumb cache). This is gitignored workspace state,
  distinct from the read-only export.

**Web (`web/`)** — new thin routers/handlers:
- `GET /api/video/{fbid}` — stream the raw `.mp4` via Starlette `FileResponse`
  (Range-enabled, so the scrubber can seek). Confined to the export root, read-only;
  404 if the fbid is not a known video or the file is missing.
- `POST /api/video/{fbid}/thumbnail` — receive a captured frame (image bytes) and write
  it to `workspace/thumbs/videos/<fbid>.jpg`. Overwrites any prior choice/default.
- `GET /api/video/{fbid}/thumbnail` — return the saved `.jpg` if present; 404 otherwise.
- **CORS:** these responses must carry the existing CORS headers so a cross-origin
  `<video crossorigin="anonymous">` can be drawn to a canvas without tainting it. The
  existing CORS middleware already applies to all routes; verified as part of testing.

**Serializers**
- `inventory_payload` gains a `videos` array: `{fbid, caption, exists}` per video
  (no `selected` — videos are not selectable). Thumbnails are fetched lazily by the
  client from `GET /api/video/{fbid}/thumbnail`.

**Selection (`selection/`)**
- Unchanged. Videos are never written to `selection.json`; they are always kept.
  The album cap/policy is untouched (videos are not album photos).

**Builder (`transform/builder.py`)**
- For each in-scope video: **do not copy the `.mp4`.** Copy
  `workspace/thumbs/videos/<fbid>.jpg` to the output at the video's path with the
  extension swapped to `.jpg` (e.g. `posts/media/videos/<fbid>.mp4` →
  `posts/media/videos/<fbid>.jpg`).
- Rewrite the `profile_posts_1.json` media URI for that video from `…<fbid>.mp4` to the
  new `…<fbid>.jpg` path so the rebuilt feed references the still image.
- **Safeguard:** a video with no saved `.jpg` (e.g. the Videos view was never opened)
  is **skipped** — the `.mp4` is *not* copied — and the fbid is reported in the build
  summary. `videos.json` remains in `DROP_JSON`.

### Frontend (`frontend/`)

**Inventory / gallery page**
- `inventory.videos` drives a new **"Videos"** entry in `AlbumList` (styled like the
  existing "Archive" entry, with a count). Selecting it sets `activeId = '__videos__'`.
- Gallery renders a video grid: `PhotoGrid` with `selectable={false}`. Video tiles show
  the chosen/default thumbnail (`videoThumbUrl(fbid)`), a **play badge**, and **no
  checkmark**. Tiles with no thumbnail yet show a play-icon placeholder.
- **Single-click** a video tile opens `VideoPreview` (not a toggle). The tile/grid needs
  a "video mode" where click = preview.

**Auto-default seeding**
- On gallery mount, a background routine iterates videos lacking a saved thumbnail,
  **sequentially and throttled**, loading each into an off-screen `<video crossorigin>`,
  seeking to ~0.1s, drawing to a canvas, and POSTing the frame as the default. Keeps the
  network from loading 21 videos at once and guarantees build-readiness.

**`VideoPreview.svelte`** (new, sibling to `PhotoPreview.svelte`)
- Modal, same shell/aesthetics as `PhotoPreview` (backdrop, close, focus trap, Esc).
- **Left:** `<video crossorigin="anonymous" src={videoUrl(fbid)}>` with play/pause and a
  timeline scrubber (second-level). Current-time readout.
- **"Choose Thumbnail"** button: draws the current video frame to a canvas
  (`videoWidth`×`videoHeight`), exports a JPEG blob, POSTs it via `saveVideoThumbnail`,
  and updates the right panel + the tile.
- **Right:** the currently chosen thumbnail image, **vertically centered** relative to
  the video on the left and rendered **30% smaller** than the video's displayed size.

**Context menu**
- For a video, `openPhotoMenu` swaps the "Preview" item for **"Choose Thumbnail"**
  (opens `VideoPreview`); "Show in File Explorer" stays. Non-video photos are unchanged.

**API (`api.js`)**
- Add `videoUrl(fbid)`, `videoThumbUrl(fbid)`, and
  `saveVideoThumbnail(fbid, blob)` (POST the captured frame).

## Data flow

```
Ingest → parse → inventory.videos (extension-detected, out of non_album)
   │
Gallery mount → background seeds default frame per video (canvas → POST)
   │
User opens a video (click or "Choose Thumbnail") → VideoPreview
   │   scrub → "Choose Thumbnail" → canvas capture → POST → workspace/thumbs/videos/<fbid>.jpg
   │
Build → for each video: copy <fbid>.jpg into output as <fbid>.jpg (never the .mp4),
        rewrite profile_posts URI .mp4 → .jpg; videos with no .jpg skipped + reported
```

## Testing (TDD, synthetic fixture)

Extend `tests/conftest.py`'s `export_root` with a video: a `videos.json` with a
`videos_v2` entry and a matching `.mp4` referenced from `profile_posts_1.json` (the file
can be a tiny dummy — the parser only checks the extension, and the stream endpoint just
serves bytes).

- **Parser:** video URIs classified as videos; `inventory.videos` populated with
  caption/title/timestamp; videos excluded from `non_album_photos`; `is_video` set.
- **Serializer:** `videos` array present; no `selected` key.
- **Video stream endpoint:** returns the bytes; 404 for unknown/missing; a Range request
  returns `206` with the requested slice.
- **Thumbnail save/get:** POST writes `workspace/thumbs/videos/<fbid>.jpg`; GET returns
  it; GET is 404 before any save.
- **Builder:** with a saved `.jpg`, the output contains `<fbid>.jpg` and **not**
  `<fbid>.mp4`, and `profile_posts` references the `.jpg`; without a saved `.jpg`, the
  video is skipped and reported and the `.mp4` is absent.
- **CORS:** the video + thumbnail responses include the `Access-Control-Allow-Origin`
  header for an allowed origin (guards canvas taint).
- **Frontend (Vitest):** context menu swaps Preview→Choose Thumbnail for videos; video
  tiles render a play badge and no checkmark; `VideoPreview` capture calls
  `saveVideoThumbnail` with a blob (canvas/video mocked).

## Output contract (unchanged intent)

Build still writes a filtered mirror to `workspace/ready/<export-name>/`; the original
export stays read-only. The only change is that video slots now hold `.jpg` stills
instead of `.mp4` files, and the rebuilt `profile_posts` references those stills.
