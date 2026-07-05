# Caption-grouped photo_albums for "Mobile uploads" & "Photos"

**Date:** 2026-07-06
**Status:** Approved design — ready for implementation plan
**Builds on:** `2026-07-05-archive-filtering-design.md` (the Archive/uncapped feature).

## Problem

`Mobile uploads` (97 kept) and `Photos` (33 kept) are flat dumps with no real album
structure, but their photos cluster tightly by caption into the original posts/photosets —
each caption leads with an editorial **headline** (e.g. *"DLSU OMBUDSMAN ISSUES MEMORANDUM…"*
×7, *"PEP-ARING FOR GLORY…"* ×5). Downstream (`this_profile's_activity_across_facebook`,
`docs/ArchersNetworkEERD.md` + `PLAN.md`) models each album as a `photo_album` keyed by
`fb_album_id` = **the trailing id of the media subdirectory** (`PLAN.md` §3.1). So today the
whole dump collapses into one meaningless `photo_album`.

Reconstruct the real photosets: within only these two albums, cluster the **kept
(non-archived)** photos by caption and emit each cluster as its own `photo_album`.

## Goals

- Auto-derive caption-grouped albums from the kept photos of `Mobile uploads` & `Photos`.
- Make each multi-photo cluster a real `photo_album` in the built `ready/` folder — its own
  media subdirectory (distinct synthetic id) + its own album JSON — so the downstream ETL,
  which derives album identity from the media **path**, sees one `photo_album` per cluster.
- Model single-photo captions as **unanchored** media (no album subdir → `fb_album_id` NULL),
  matching the EERD's "standalone-post image" model.

## Non-goals

- No change to Archive (news-tag set-aside) — grouping runs **after** archiving and only sees
  what remains. No change to other albums or to already-unanchored non-album photos.
- No manual grouping UI, no merge/split/rename — grouping is fully automatic from captions.
- No downstream ETL change — album identity is carried entirely through the media **path**
  (the reason we physically regroup media, below).

## Key decisions (resolved during brainstorming)

| Decision | Choice |
|---|---|
| How albums form | **Auto-derive** by clustering identical captions. |
| Scope | **Only kept (non-archived)** photos in the two special albums. |
| Output impact | **Write real `photo_album`s** (per-group media subdir + album JSON). |
| Album identity | **Physically regroup media**; synthetic `fb_album_id` = the group's first photo `fbid`. |
| Single-photo captions | **Unanchored** — copied as loose media (no album subdir); join the auto-kept bucket. |
| No-caption photos (edge) | Also unanchored (nothing to group on). |
| Cap on derived albums | **Uncapped** (they descend from the two albums chosen to be unlimited; sets are small). |
| Left-rail UI | Flat albums grouped under a lightweight **origin subheader** (not collapsible nesting). |

## Definitions

**Caption key** — `caption.strip()` (mojibake already fixed by the parser). Photos with the
same non-empty key belong to the same group.

**Headline** — the caption's first non-empty line, trimmed, truncated to 100 chars. Used as
the derived album's display `name`. Real remaining captions are `HEADLINE\n\nTAG: body`, so
the first line is the headline (news-tag captions are already gone to Archive).

**Synthetic album id** — the `fbid` of the group's first photo (in original album order). A
real, unique FB numeric id, stable across rebuilds; used as `fb_album_id` and as the media
subdir's trailing id so the downstream derives it from the path.

**Media slug** — `<AlnumHeadline>_<synthId>` (headline reduced to alphanumerics, ≤30 chars, no
`_`; then `_` + synthetic id). The per-group media subdirectory name, mirroring FB's
`<Album>_<albumFbid>` convention so `album_id_from_uri` yields the synthetic id.

## Architecture

### 1. `inventory/grouping.py` (new — pure, unit-tested)

```python
def caption_headline(caption: str) -> str: ...          # first non-empty line, trimmed, ≤100
def media_slug(headline: str, synth_id: str) -> str: ... # "<AlnumHeadline>_<synthId>"
def derive_caption_albums(inventory: ExportInventory) -> None: ...
```

`derive_caption_albums` mutates the inventory in place. For each album with `uncapped=True`
(i.e. the two special albums, set by `partition_archive`):
- Group its photos by caption key, preserving first-seen order.
- **Group of ≥2 with a non-empty caption →** a derived `Album`: `fb_album_id` = first photo's
  `fbid`; `name` = `caption_headline`; `origin` = the parent album's name; `uncapped=True`;
  `media_slug` = `media_slug(headline, synth_id)`. Each member photo gets `album_fbid` = the
  synthetic id and `ready_uri` = `posts/media/<media_slug>/<fbid>.jpg`.
- **Group of 1, or any no-caption photo →** the photo becomes **unanchored**: `album_fbid`
  set to `None`, `ready_uri` = `posts/media/<fbid>.jpg` (loose, no subdir), and it is appended
  to `inventory.non_album_photos`.
- The original single special-album entry is **removed** from `inventory.albums`; its derived
  albums are inserted in its place (grouped contiguously so the UI can subhead them).

### 2. `inventory/models.py`

- `Album` gains `origin: str | None = None` (parent dump name, for the UI subheader) and
  `media_slug: str | None = None` (the derived subdir; `None` for real FB albums).
- `Photo` gains `ready_uri: str | None = None` — destination path (relative, from `posts/`)
  in the ready folder. `None` means "copy in place at the original path". Set by grouping for
  regrouped and loosened photos. Keeps the builder's retargeting data on the photo itself.

### 3. `inventory/parser.py`

`build_inventory` calls, in order: parse → `partition_archive(inventory)` (existing) →
`derive_caption_albums(inventory)` (new). Both the UI and the build see the identical result.

### 4. `web/serializers.py`

Each album dict gains `"origin": a.origin`. Derived albums serialize like any album (their
synthetic `fb_album_id` keys selection; `max_per_album` is `None` because `uncapped`).

### 5. `transform/builder.py` — the real work

Destinations come from `photo.ready_uri` (set by grouping) or the original path when `None`.

1. **Copy media** — for each kept photo, copy the source (`resolve_uri(original_uri)`) to
   `dest / (ready_uri or <uri-from-"posts/">)`. Derived-album photos land in their
   `<slug>_<id>/` subdir; singletons land loose directly under `posts/media/`.
2. **Album JSONs:**
   - **Derived albums** — synthesize `posts/album/<synthId>.json` = `{name: headline,
     photos: [{uri: p.ready_uri, creation_timestamp, title} for kept+present photos]}`. Skip a
     group with nothing kept.
   - **Original albums** — as today (read each source `album/*.json`, filter to kept), **but
     skip source files whose `name` `is_special_album`** — those are replaced by derived albums.
3. **profile_posts** — filter attachments to present media (existing), and for any kept photo
   with a `ready_uri`, **rewrite `media.uri` to the new path** so the feed and the album files
   agree on the path-derived `fb_album_id` (`PLAN.md` §3.1). Then drop media-less posts
   (existing). Archived photos remain excluded (existing).

Other albums, orphan handling, and the read-only-original guarantee are unchanged.

## Data flow

```
build_inventory
  → parse albums + non-album
  → partition_archive        # news-tag photos → archived_photos (Archive)
  → derive_caption_albums     # per uncapped album: ≥2 same-caption → derived photo_album;
                              #   singleton/no-caption → unanchored (non_album); set ready_uri
UI:    serializers → albums (derived carry origin, uncapped) + archive[] + non_album[]
Build: copy media to ready_uri | write per-group album JSON | rewrite feed uris | drop empties
```

## UI (`frontend/`)

Derived albums are ordinary albums and reuse the entire album UI (grid, selection, preview,
uncapped handling from the prior feature). In `AlbumList`, albums that share an `origin` render
under a small uppercase subheader (`Mobile uploads`, `Photos`); albums with no `origin` render
as today. Unanchored singletons fold into the existing **Auto-kept** count.

## Testing (TDD)

- `tests/inventory/test_grouping.py` — `caption_headline` (multi-line, emoji, single-line
  fallback, truncation); `media_slug` shape (trailing id = synth id); `derive_caption_albums`
  on a hand-built inventory: ≥2 → derived album (id, name, origin, uncapped, `ready_uri`);
  singleton and no-caption → `non_album` with loose `ready_uri`; a non-`uncapped` album with a
  shared caption is untouched.
- `tests/inventory/test_parser.py` — pipeline order on a new `grouping_export_root` fixture:
  the special album is replaced by its derived albums, singletons land in `non_album`, archived
  photos still set aside first.
- `tests/transform/test_builder.py` — derived group's media in its `<slug>_<id>/` subdir + a
  per-group album JSON present; singleton media loose (no subdir) with no album JSON; original
  special-album JSON absent; feed uris rewritten to new paths; archived still excluded; empty
  posts dropped.
- `tests/web/test_serializers.py` — derived album carries `origin`, cap `null`.
- **Fixture** — new `grouping_export_root` (`conftest.py`) with a 2-photo caption group, a
  3-photo group, a singleton caption, a no-caption photo, a news-tag photo (archived first),
  and a normal capped album sharing a caption (must stay untouched).
- **Refactors** (pipeline changed): the archive-partition assertion moves to a direct unit
  test of `partition_archive` on a hand-built inventory (decoupled from the new stage), and the
  uncapped-serialization route test retargets to the grouping fixture's derived albums.
- Frontend (`vitest`) — `AlbumList` renders the origin subheader and a derived album selects
  normally.

## Risks / edge cases

- **Album id == a photo fbid.** The synthetic album id equals the group's first photo's fbid;
  that photo's `media` row then has `fbid == fb_album_id`. Different tables/columns, so valid —
  just a coincidence worth noting.
- **Singletons become auto-kept.** Moving single-photo captions into the non-album bucket makes
  them auto-kept (no longer hand-picked) — the accepted consequence of "unanchored".
- **Duplicate headlines.** Two different captions with the same first line yield two albums with
  the same display `name` but distinct ids/media slugs — acceptable and rare.
- **Feed/album path agreement.** The feed-uri rewrite (§5.3) is required; without it the ETL
  could derive a different `fb_album_id` from the post copy than from the album file.
