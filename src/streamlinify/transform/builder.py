from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
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
    videos_built: int = 0
    skipped_videos: list[str] = field(default_factory=list)


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


def build_ready_folder(
    export_root: Path, dest: Path, keep_fbids: set[str], video_thumb_dir: Path | None = None,
    renames: dict[str, str] | None = None
) -> BuildResult:
    inventory = build_inventory(export_root)
    if renames:
        for album in inventory.albums:
            if album.fb_album_id in renames:
                album.name = renames[album.fb_album_id]
    # Archived (news-caption) photos and manually archived albums are set aside — never
    # carried into the build, even if a stale selection.json still names one.
    keep_fbids = keep_fbids - {p.fbid for p in inventory.archived_photos}
    keep_fbids = keep_fbids - {p.fbid for a in inventory.archived_albums for p in a.photos}
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

    # Videos: never copy the .mp4. Copy the chosen still into the video's slot as a
    # .jpg and remember the rewritten uri so the feed points at the image. A video
    # with no chosen still is skipped and reported (the .mp4 is never a fallback).
    video_ready: dict[str, str] = {}
    skipped_videos: list[str] = []
    videos_built = 0
    for video in inventory.videos:
        if video.fbid not in keep_fbids:
            continue
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
        if renames and album_path.stem in renames:
            out["name"] = renames[album_path.stem]
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
                    if fbid in video_ready:
                        d["media"]["uri"] = video_ready[fbid]
                        kept_data.append(d)
                        continue
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

    return BuildResult(
        ready_root=dest,
        copied=copied,
        albums_written=albums_written,
        orphans=orphans,
        videos_built=videos_built,
        skipped_videos=skipped_videos,
    )
