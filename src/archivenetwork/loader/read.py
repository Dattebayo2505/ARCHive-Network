"""Reconstruct DB rows from the ready folder — and *only* the ready folder.

The downstream ETL will have a folder and nothing else, so this module must never reach for
`build_inventory()` or the live `Session`. It imports only the pure FB-export helpers, which
are the documented rules themselves; reusing them prevents drift without weakening the proof
that the ready folder stands alone.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..inventory.hashtags import canonical_tag, slugify, split_hashtags
from ..inventory.parser import album_id_from_uri, photo_fbid
from ..inventory.text import epoch_to_dt, fix_mojibake


@dataclass
class AlbumRow:
    fb_album_id: str
    title: str
    # The post body every member photo shares, or the caption editor's override when one
    # exists. It rides into the ready folder as the album JSON's `description` key — the
    # FB-shaped wire name — but here it is what it means: the album's caption.
    caption: str | None
    date: datetime | None
    is_derived: bool
    hashtag: str | None = None


@dataclass
class MediaRow:
    fbid: str
    media_type: str  # 'photo' | 'video'
    fb_album_id: str | None
    title: str | None
    # An *override*, not the usual home. Album-anchored media leaves this NULL and inherits
    # `AlbumRow.caption`; only album-less media (videos, legacy unanchored) fills it in.
    caption: str | None
    uri: str  # 'posts/media/...' — both the path under ready/ and the original_fb_uri
    creation_at: datetime | None
    hashtag: str | None = None
    group: str = "unanchored"  # the object-key's second segment: album slug | videos | unanchored


@dataclass
class ReadResult:
    albums: list[AlbumRow]
    media: list[MediaRow]


def _clean(s: str | None) -> str | None:
    """Decode mojibake, strip hashtags, and normalise empty strings to None.

    The ready folder is *mixed*: derived album names are already decoded, while post bodies and
    video descriptions are still raw. `fix_mojibake` is idempotent on already-decoded text, so
    applying it uniformly is safe and we needn't track which is which.

    Hashtags are stripped here, at the ETL's mouth, so Postgres stores clean prose. They are
    NOT stripped from the ready folder, which stays a faithful FB-shaped mirror.
    """
    if not s:
        return None
    prose, _tags_found = split_hashtags(fix_mojibake(s))
    return prose or None


def _tags(s: str | None) -> list[str]:
    """The hashtags in one raw string, decoded first."""
    if not s:
        return []
    _prose, tags = split_hashtags(fix_mojibake(s))
    return tags


def _read_videos(posts: Path) -> dict[str, dict]:
    """videos.json — the explicit video marker. A poster is otherwise an ordinary .jpg."""
    path = posts / "videos.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {photo_fbid(v["uri"]): v for v in raw.get("videos_v2", [])}


def _read_unanchored(posts: Path) -> list[dict]:
    """unanchored.json — media belonging to no album.

    A loose photo that was also posted is reachable via the feed too; one that was never posted
    (no caption) appears **only** here. Without this manifest such a photo is copied into ready/
    and referenced by nothing, so a manifest-driven ETL would silently drop it.
    """
    path = posts / "unanchored.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("photos", [])


def _read_feed(posts: Path) -> dict[str, dict]:
    """profile_posts_1.json — the source of captions, post timestamps, and unanchored media."""
    path = posts / "profile_posts_1.json"
    if not path.exists():
        return {}
    feed: dict[str, dict] = {}
    for post in json.loads(path.read_text(encoding="utf-8")):
        post_ts = post.get("timestamp")
        body = ""
        for d in post.get("data", []):
            if "post" in d:
                body = d["post"]
        for att in post.get("attachments", []):
            for d in att.get("data", []):
                media = d.get("media")
                if not media or "uri" not in media:
                    continue
                feed[photo_fbid(media["uri"])] = {
                    "uri": media["uri"],
                    "caption": _clean(body),
                    "raw_caption": body,  # tags survive here; `caption` is already stripped
                    "title": _clean(media.get("title")),
                    "post_ts": post_ts,
                    "creation_ts": media.get("creation_timestamp"),
                }
    return feed


def read_ready(ready_root: Path) -> ReadResult:
    posts = ready_root / "posts"
    videos = _read_videos(posts)
    feed = _read_feed(posts)

    albums: list[AlbumRow] = []
    media: dict[str, MediaRow] = {}

    for album_path in sorted((posts / "album").glob("*.json")):
        raw = json.loads(album_path.read_text(encoding="utf-8"))
        photos = raw.get("photos", [])
        if not photos:
            continue
        # The album id comes from the media subdir in the PATH — never the JSON filename
        # (named FB albums are 0.json..11.json, whose stems are meaningless).
        album_id = album_id_from_uri(photos[0]["uri"])
        if album_id is None:
            continue
        # The album's caption and tag come from the same raw string: its `description` when the
        # JSON carries one — the builder writes only {"name", "photos"} unless a volunteer
        # edited the caption, so that key present *means* an override — else the shared post
        # body of its member photos.
        raw_caption = raw.get("description")
        if not raw_caption:
            raw_caption = next(
                (
                    body
                    for p in photos
                    if (body := feed.get(photo_fbid(p["uri"]), {}).get("raw_caption"))
                ),
                None,
            )
        # Tags are re-scanned across every photo rather than read off `raw_caption` alone: a
        # first photo whose body happens to be untagged must not cost the album its section.
        tags = _tags(raw_caption)
        if not tags:
            for p in photos:
                tags = _tags(feed.get(photo_fbid(p["uri"]), {}).get("raw_caption"))
                if tags:
                    break
        album_tag = canonical_tag(tags)
        album_title = _clean(raw.get("name")) or album_id
        album_group = slugify(album_title) or album_id

        albums.append(
            AlbumRow(
                fb_album_id=album_id,
                title=album_title,
                caption=_clean(raw_caption),
                date=None,  # backfilled below from the album's earliest media
                # A derived caption-album is written as <synthId>.json, so its stem IS its id.
                is_derived=album_path.stem == album_id,
                hashtag=album_tag,
            )
        )
        for p in photos:
            fbid = photo_fbid(p["uri"])
            hit = feed.get(fbid, {})
            ts = hit.get("post_ts") or p.get("creation_timestamp")
            media[fbid] = MediaRow(
                fbid=fbid,
                media_type="photo",
                fb_album_id=album_id,
                title=_clean(p.get("title")),
                caption=None,  # inherits the album's; the override is for album-less media
                uri=p["uri"],
                creation_at=epoch_to_dt(ts) if ts else None,
                hashtag=album_tag,
                group=album_group,
            )

    # Feed-only media: unanchored photos and the video posters. These are the rows the caption
    # override exists for — a video is never album-anchored in practice, so there is nothing to
    # inherit from. Guard on the album ids actually emitted above, not merely on a parsed id:
    # an id with no AlbumRow behind it would drop the caption into a hole.
    known_albums = {a.fb_album_id for a in albums}
    for fbid, hit in feed.items():
        if fbid in media:
            continue
        video = videos.get(fbid)
        ts = hit.get("post_ts") or hit.get("creation_ts")
        own_tags = _tags(hit.get("raw_caption")) or _tags((video or {}).get("description"))
        album_id = album_id_from_uri(hit["uri"])  # None for posts/media/<fbid>.jpg
        own_caption = hit.get("caption") or _clean((video or {}).get("description"))
        media[fbid] = MediaRow(
            fbid=fbid,
            media_type="video" if video else "photo",
            fb_album_id=album_id,
            title=hit.get("title"),
            caption=None if album_id in known_albums else own_caption,
            uri=hit["uri"],
            creation_at=epoch_to_dt(ts) if ts else None,
            hashtag=canonical_tag(own_tags),
            group="videos" if video else "unanchored",
        )

    # Videos listed in videos.json but absent from the feed (defensive; not seen in practice).
    for fbid, video in videos.items():
        if fbid in media:
            continue
        ts = video.get("creation_timestamp")
        media[fbid] = MediaRow(
            fbid=fbid,
            media_type="video",
            fb_album_id=None,
            title=_clean(video.get("title")),
            caption=_clean(video.get("description")),
            uri=video["uri"],
            creation_at=epoch_to_dt(ts) if ts else None,
            hashtag=canonical_tag(_tags(video.get("description"))),
            group="videos",
        )

    # Unanchored media. Added last, so where a loose photo is *also* in the feed the feed's
    # richer record (it carries the caption) already won; this only picks up the never-posted
    # ones, which no other manifest mentions.
    for rec in _read_unanchored(posts):
        fbid = photo_fbid(rec["uri"])
        if fbid in media:
            continue
        ts = rec.get("creation_timestamp")
        media[fbid] = MediaRow(
            fbid=fbid,
            media_type="photo",
            fb_album_id=album_id_from_uri(rec["uri"]),  # None for posts/media/<fbid>.jpg
            title=_clean(rec.get("title")),
            caption=None,  # never posted -> there is no post body to hoist
            uri=rec["uri"],
            creation_at=epoch_to_dt(ts) if ts else None,
        )

    # An album's date is its earliest media timestamp.
    earliest: dict[str, datetime] = {}
    for m in media.values():
        if m.fb_album_id and m.creation_at:
            current = earliest.get(m.fb_album_id)
            if current is None or m.creation_at < current:
                earliest[m.fb_album_id] = m.creation_at
    for a in albums:
        a.date = earliest.get(a.fb_album_id)

    return ReadResult(albums=albums, media=list(media.values()))
