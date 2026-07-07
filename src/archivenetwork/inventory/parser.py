from __future__ import annotations

import json
from pathlib import Path

from .archive import partition_archive
from .grouping import derive_caption_albums
from .models import Album, ExportInventory, Photo
from .text import epoch_to_dt, fix_mojibake


_VIDEO_EXTS = {".mp4", ".mov", ".webm"}


def is_video_uri(uri: str) -> bool:
    return Path(uri).suffix.lower() in _VIDEO_EXTS


def resolve_uri(uri: str, export_root: Path) -> Path:
    idx = uri.find("posts/")
    rel = uri[idx:] if idx != -1 else uri
    return export_root / rel


def photo_fbid(uri: str) -> str:
    return Path(uri).stem


def album_id_from_uri(uri: str) -> str | None:
    parent = Path(uri).parent.name  # e.g. "AnimoFest_111"
    if "_" not in parent:
        return None
    tail = parent.rsplit("_", 1)[1]
    return tail or None


def extract_taken_ts(media: dict) -> int | None:
    try:
        md = media.get("media_metadata", {})
        if "photo_metadata" in md:
            return md["photo_metadata"]["exif_data"][0].get("taken_timestamp")
    except (KeyError, IndexError, TypeError):
        pass
    return None


def _post_media_records(export_root: Path) -> list[dict]:
    """Flatten profile_posts into {uri, title, caption, creation_timestamp} dicts."""
    path = export_root / "posts" / "profile_posts_1.json"
    if not path.exists():
        return []
    posts = json.loads(path.read_text(encoding="utf-8"))
    records: list[dict] = []
    for post in posts:
        post_ts = post.get("timestamp")
        body = ""
        for d in post.get("data", []):
            if "post" in d:
                body = fix_mojibake(d["post"])
        for att in post.get("attachments", []):
            for d in att.get("data", []):
                media = d.get("media")
                if not media or "uri" not in media:
                    continue
                records.append(
                    {
                        "uri": media["uri"],
                        "title": fix_mojibake(media.get("title", "")),
                        "caption": body,
                        "creation_timestamp": media.get("creation_timestamp"),
                        "post_timestamp": post_ts,
                        "taken_timestamp": extract_taken_ts(media),
                    }
                )
    return records


def build_inventory(export_root: Path) -> ExportInventory:
    post_records = _post_media_records(export_root)
    meta_map = {
        photo_fbid(r["uri"]): {
            "caption": r["caption"],
            "post_ts": r["post_timestamp"],
            "taken_ts": r["taken_timestamp"]
        }
        for r in post_records
    }

    albums: list[Album] = []
    album_fbids: set[str] = set()
    for album_path in sorted((export_root / "posts" / "album").glob("*.json")):
        raw = json.loads(album_path.read_text(encoding="utf-8"))
        photos: list[Photo] = []
        derived_album_id: str | None = None
        for rec in raw.get("photos", []):
            uri = rec["uri"]
            fbid = photo_fbid(uri)
            album_id = album_id_from_uri(uri)
            derived_album_id = derived_album_id or album_id
            resolved = resolve_uri(uri, export_root)
            ts = rec.get("creation_timestamp")
            meta = meta_map.get(fbid, {})
            taken_ts = extract_taken_ts(rec) or meta.get("taken_ts")
            photos.append(
                Photo(
                    fbid=fbid,
                    original_uri=uri,
                    resolved_path=resolved,
                    title=fix_mojibake(rec.get("title", "")),
                    caption=meta.get("caption"),
                    creation_at=epoch_to_dt(ts) if ts else None,
                    post_timestamp=epoch_to_dt(meta.get("post_ts")) if meta.get("post_ts") else None,
                    taken_timestamp=epoch_to_dt(taken_ts) if taken_ts else None,
                    album_fbid=album_id,
                    exists=resolved.exists(),
                    file_size_bytes=resolved.stat().st_size if resolved.exists() else 0,
                )
            )
            album_fbids.add(fbid)
        
        album_post_ts = None
        for p in photos:
            if p.post_timestamp:
                album_post_ts = p.post_timestamp
                break

        albums.append(
            Album(
                fb_album_id=derived_album_id or album_path.stem,
                name=fix_mojibake(raw.get("name", album_path.stem)),
                description=fix_mojibake(raw.get("description", "")),
                photos=photos,
                post_timestamp=album_post_ts,
            )
        )

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
            post_timestamp=epoch_to_dt(r.get("post_timestamp")) if r.get("post_timestamp") else None,
            taken_timestamp=epoch_to_dt(r.get("taken_timestamp")) if r.get("taken_timestamp") else None,
            album_fbid=None,
            exists=resolved.exists(),
            file_size_bytes=resolved.stat().st_size if resolved.exists() else 0,
            is_video=is_video_uri(r["uri"]),
        )
        (videos if photo.is_video else non_album).append(photo)

    inventory = ExportInventory(albums=albums, non_album_photos=non_album, videos=videos)
    partition_archive(inventory)
    derive_caption_albums(inventory)
    return inventory
