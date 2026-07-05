# Archive filtering for "Mobile uploads" & "Photos"

**Date:** 2026-07-05
**Status:** Approved design — ready for implementation plan

## Problem

The Archers Network Facebook export contains two large "dump" albums — **`Mobile uploads`**
(148 photos) and **`Photos`** (44 photos) — that mix ordinary gallery photos with the
publication's news posts. News posts are conventionally captioned with an UPPERCASE tag
(`BREAKING:`, `LOOK:`, `HAPPENING NOW:`, …). In the real export, 22 of the 65 posts that
reference these two albums' photos carry such a tag.

Two problems follow:

1. The ≤10-per-album cap is wrong for these two albums — they are curation targets, not
   themed albums, and the volunteer needs to pick freely from them.
2. The news-tagged photos should be **set aside** (archived), not carried into the
   uploaded set. Today there is no way to separate them.

## Goals

- Remove the 10-photo cap on `Mobile uploads` and `Photos` only. Other albums keep the cap.
- Within only those two albums, detect news-tagged photos by caption and move them into a
  new **Archive** section that is **read-only** and **excluded from the build**.
- Fix a related builder correctness gap: posts that end up with no surviving media must be
  dropped from the ready `profile_posts_1.json`, not left as orphaned text-only records.

## Non-goals

- No change to other albums or to the non-album "Auto-kept" bucket.
- No "rescue"/un-archive UI — the Archive is review-only. Archiving is fully automatic
  from captions.
- No scanning of non-album photos or non-special albums for tags.

## Key decisions (resolved during brainstorming)

| Decision | Choice |
|---|---|
| What happens to archived photos in the build? | **Set aside — excluded** from `ready/`. |
| Caption match rule | **UPPERCASE prefix, whole-word.** |
| Remaining (non-archived) photos in the two albums | **Hand-pick, no cap.** Nothing auto-kept. |
| Media-less posts in the output | **Dropped** (general builder fix; safe — every post in the export is media-anchored). |

## Definitions

**Special albums** — albums whose name, normalized (`strip().casefold()`), is in
`{"mobile uploads", "photos"}`. Real export names: `Mobile uploads`, `Photos`.

**Archive keywords** — `COURTESY`, `HAPPENING NOW`, `JUST IN`, `LOOK`, `WATCH`, `BREAKING`,
`UPDATE`, `REST IN PEACE`.

**Caption** — a photo's caption is the body text of the post it was attached to (already
resolved by `parser.py` via `caption_map`). No new data source.

**Archive match** — a caption matches iff, after stripping leading non-letter characters
(emoji, whitespace, punctuation), it **starts with** one of the keywords **case-sensitively**,
and the character immediately after the keyword is a non-letter or end-of-string. This
matches `BREAKING: …`, `🚨 LOOK: …`, `HAPPENING NOW: …`, `REST IN PEACE.`; and rejects
`Look at this`, `We were watching`, `Updated our schedule`, `LOOKING`, lowercase tags.

## Architecture

### 1. `inventory/archive.py` (new — pure, unit-tested)

Isolates all classification rules so they can change without touching the parser, policy,
or web layers (mirrors how `selection/policy.py` isolates the cap rule).

```python
SPECIAL_ALBUM_NAMES = frozenset({"mobile uploads", "photos"})
ARCHIVE_KEYWORDS = ("HAPPENING NOW", "REST IN PEACE", "JUST IN",
                    "BREAKING", "COURTESY", "UPDATE", "WATCH", "LOOK")

def is_special_album(name: str) -> bool: ...
def archive_tag(caption: str | None) -> str | None: ...
def partition_archive(inventory: ExportInventory) -> None: ...
```

- `ARCHIVE_KEYWORDS` is ordered **longest-phrase-first** so multi-word tags are tested
  before any single-word prefix they might share (defensive; no current overlap).
- `archive_tag` returns the matched keyword (used as the display badge) or `None`.
- `partition_archive` mutates the inventory in place: for each album where
  `is_special_album(album.name)`, set `album.uncapped = True`, then split its photos —
  matching photos get `archived=True`, `archive_tag=<kw>`, are **removed** from
  `album.photos`, and are appended to `inventory.archived_photos`. Order preserved.

### 2. `inventory/models.py`

- `Photo`: add `archived: bool = False`, `archive_tag: str | None = None`.
- `Album`: add `uncapped: bool = False`.
- `ExportInventory`: add `archived_photos: list[Photo] = []`. `all_photos()` now also
  includes `archived_photos` so `/api/thumb`, `/api/preview`, and `/api/reveal` lookups
  (which go through `photo_by_fbid`) resolve archived photos for the read-only viewer.

### 3. `inventory/parser.py`

At the end of `build_inventory`, call `partition_archive(inventory)` before returning.
Because the build path (`transform/builder.py`) also calls `build_inventory`, the UI and
the build see an **identical** archived set — no drift.

### 4. `selection/policy.py`

```python
@dataclass
class DefaultPolicy:
    max_per_album: int = settings.max_per_album
    uncapped_albums: frozenset[str] = frozenset()

    def can_select(self, album_fbid: str, current_count: int) -> bool:
        if album_fbid in self.uncapped_albums:
            return True
        return current_count < self.max_per_album
```

`web/routes_ingest.py::_start_session` builds the set from the freshly parsed inventory:

```python
inventory = build_inventory(export_root)
uncapped = frozenset(a.fb_album_id for a in inventory.albums if a.uncapped)
selection = SelectionState(workspace / "selection.json",
                           DefaultPolicy(uncapped_albums=uncapped))
```

### 5. `transform/builder.py` + `web/routes_build.py`

Two changes, both correctness:

1. **Exclude archived (defense-in-depth).** In the build route, subtract archived fbids
   from `keep` so a stale `selection.json` written before this feature cannot leak an
   archived photo through:
   ```python
   keep -= {p.fbid for p in session.inventory.archived_photos}
   ```
   (Archived photos are already never selectable in the UI; this guards persisted state.)

2. **Drop media-less posts.** After filtering each post's attachments to present media,
   drop any post that retains no attachments:
   ```python
   posts = [p for p in posts if p.get("attachments")]
   ```
   A post survives iff ≥1 attachment retains kept-and-present media (uses the existing
   `present_fbids` = kept ∧ exists-on-disk set). This uniformly covers archived,
   non-selected, and orphaned posts. Safe: every post in the export is media-anchored, so
   no legitimate text-only post is removed.

### 6. `web/serializers.py`

- Each album dict gains `"max_per_album": None if a.uncapped else max_per_album`
  (`None` → unlimited; the top-level `max_per_album` stays for capped albums).
- Payload gains:
  ```python
  "archive": [
      {"fbid": p.fbid, "caption": p.caption, "archive_tag": p.archive_tag,
       "exists": p.exists}
      for p in inventory.archived_photos
  ]
  ```

### 7. Frontend (`frontend/src/`)

- **`AlbumList.svelte`** — add an **Archive** nav row (count = `archive.length`) that
  selects a sentinel id `'__archive__'`, placed with the Auto-kept row. For uncapped
  albums, render the badge as the selected count with an `∞` affordance instead of
  `n / 10`.
- **`gallery/+page.svelte`**:
  - When `activeId === '__archive__'`, render a **read-only** Archive grid — thumbnail +
    caption + tag badge, right-click → Preview / Show in File Explorer, **no** selecting,
    **no** cap/fill bar.
  - For an active **uncapped** album, hide the fill bar and `/max` text, show
    "N selected", and allow unlimited toggles (`activeFull` is never true when the album's
    `max_per_album` is `null`).
  - Cap logic keys off the album's own `max_per_album` (nullable) instead of the single
    top-level value.
- New **`ArchiveGrid.svelte`** (or a read-only mode of `PhotoGrid.svelte`) for the grid.

## Data flow

```
build_inventory(export_root)
  → parse albums + non-album (existing)
  → partition_archive(inventory)              # marks uncapped, moves tagged photos out
      ├─ inventory.albums[special].photos     # non-archived only (uncapped)
      ├─ inventory.albums[special].uncapped=T
      └─ inventory.archived_photos            # tagged, read-only

UI:  serializers → albums (per-album cap) + archive[] + non_album[]
Build: keep = selected ∪ present-non-album,  keep -= archived
       → copy media, rewrite album JSONs, filter posts, DROP empty posts
```

## Testing (TDD)

Backend (`pytest`, synthetic fixture only):

- `tests/test_archive.py` — `is_special_album` (name normalization); `archive_tag`
  positives (`BREAKING:`, `🚨 LOOK:`, `HAPPENING NOW:`, `REST IN PEACE.`) and the tricky
  negatives (`Look at this`, `watching`, `Updated`, `LOOKING`, lowercase, `None`/empty).
- `tests/test_parser.py` — a matching photo in a special album lands in
  `archived_photos`, is removed from `album.photos`, album is `uncapped`; a non-matching
  photo stays; a matching caption in a **non-special** album is left untouched.
- `tests/test_policy.py` — an uncapped album selects past `max_per_album`; a normal album
  still raises `CapExceeded` at the cap.
- `tests/test_serializers.py` (or web) — payload has `archive`; uncapped album cap `None`;
  capped album cap unchanged.
- `tests/test_builder.py` — (a) an archived fbid present in a stale selection is **not**
  copied; (b) a post whose only photo is archived disappears from output
  `profile_posts_1.json`; (c) a post with one kept + one archived photo survives with just
  the kept media.
- **Fixture (`tests/conftest.py`)** — add real `Mobile uploads` and `Photos` **albums**
  (album JSONs + media), plus posts supplying matching and non-matching captions for their
  photos. Update existing count assertions affected by the new albums.

Frontend (`vitest`):

- Light test that the Archive nav row renders its count and that an uncapped album tile
  shows no `/10` ceiling.

## Risks / edge cases

- **Album identity by name.** Matching is by normalized name, not a stable fb id, because
  the album's `fb_album_id` is not knowable ahead of time. If Facebook renames these
  albums in a future export, the constant set must be updated. Documented in
  `inventory/archive.py`.
- **`UPDATE` vs `UPDATED`.** Whole-word matching intentionally excludes `UPDATED:` (char
  after `UPDATE` is a letter). Accepted per the "precise match" decision; revisit only if
  real captions use inflected tags.
- **Stale `selection.json`.** Handled by the build-route subtraction (§5.1).
