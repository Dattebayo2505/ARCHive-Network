from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

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


def _copy_media(uri: str, export_root: Path, dest: Path) -> bool:
    src = resolve_uri(uri, export_root)
    if not src.exists():
        return False
    idx = uri.find("posts/")
    rel = uri[idx:] if idx != -1 else uri
    target = dest / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    return True


def build_ready_folder(export_root: Path, dest: Path, keep_fbids: set[str]) -> BuildResult:
    inventory = build_inventory(export_root)
    dest.mkdir(parents=True, exist_ok=True)

    copied = 0
    orphans: list[str] = []

    # Copy kept media (album + non-album), tracking orphans.
    for photo in inventory.all_photos():
        if photo.fbid not in keep_fbids:
            continue
        if _copy_media(photo.original_uri, export_root, dest):
            copied += 1
        else:
            orphans.append(photo.original_uri)

    present_fbids = {
        photo.fbid for photo in inventory.all_photos() if photo.fbid in keep_fbids and photo.exists
    }

    # Rewrite album JSONs to kept photos; skip albums with nothing kept.
    albums_written = 0
    album_src_dir = export_root / "posts" / "album"
    album_dst_dir = dest / "posts" / "album"
    for album_path in sorted(album_src_dir.glob("*.json")):
        raw = json.loads(album_path.read_text(encoding="utf-8"))
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

    # Filter profile_posts to kept + present media.
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
        (dest / "posts").mkdir(parents=True, exist_ok=True)
        (dest / "posts" / "profile_posts_1.json").write_text(
            json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return BuildResult(ready_root=dest, copied=copied, albums_written=albums_written, orphans=orphans)
