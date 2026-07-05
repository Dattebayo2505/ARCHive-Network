import json
from pathlib import Path

from streamlinify.transform.builder import build_ready_folder


def test_build_filtered_mirror(export_root: Path, tmp_path: Path):
    dest = tmp_path / "ready"
    # keep 2 album-111 photos + both non-album (m01 present, m02 orphan)
    keep = {"a01", "a02", "m01", "m02"}
    result = build_ready_folder(export_root, dest, keep)

    # album 0 rewritten to exactly the 2 kept photos
    album0 = json.loads((dest / "posts" / "album" / "0.json").read_text(encoding="utf-8"))
    assert {Path(p["uri"]).stem for p in album0["photos"]} == {"a01", "a02"}

    # album 1 had 0 kept photos → not written
    assert not (dest / "posts" / "album" / "1.json").exists()

    # media copied for present files only; m02 is an orphan
    assert (dest / "posts" / "media" / "AnimoFest_111" / "a01.jpg").exists()
    assert (dest / "posts" / "media" / "Mobileuploads_999" / "m01.jpg").exists()
    assert not (dest / "posts" / "media" / "Mobileuploads_999" / "m02.jpg").exists()
    assert result.copied == 3
    assert any("m02" in o for o in result.orphans)

    # unnecessary JSONs dropped
    assert not (dest / "posts" / "videos.json").exists()

    # profile_posts filtered to kept + present media
    posts = json.loads((dest / "posts" / "profile_posts_1.json").read_text(encoding="utf-8"))
    kept_uris = {
        Path(d["media"]["uri"]).stem
        for post in posts
        for att in post.get("attachments", [])
        for d in att.get("data", [])
    }
    assert kept_uris == {"a01", "a02", "m01"}

    # original untouched
    assert (export_root / "posts" / "videos.json").exists()


def test_idempotent_rerun(export_root: Path, tmp_path: Path):
    dest = tmp_path / "ready"
    build_ready_folder(export_root, dest, {"a01"})
    result = build_ready_folder(export_root, dest, {"a01"})
    assert result.copied == 1


def test_build_excludes_archived_and_drops_empty_posts(archive_export_root: Path, tmp_path: Path):
    dest = tmp_path / "ready"
    # A stale keep set that even names the archived photos u01 / p01.
    keep = {"u01", "u02", "u03", "p01", "p02", "a01"}
    build_ready_folder(archive_export_root, dest, keep)

    # Archived photos are never copied, even though present + in keep.
    assert not (dest / "posts" / "media" / "Mobileuploads_555" / "u01.jpg").exists()
    assert not (dest / "posts" / "media" / "Photos_666" / "p01.jpg").exists()
    # Non-archived kept photos are copied (u02 is now unanchored → loose path).
    assert (dest / "posts" / "media" / "u02.jpg").exists()

    posts = json.loads((dest / "posts" / "profile_posts_1.json").read_text(encoding="utf-8"))
    bodies = [d["post"] for post in posts for d in post.get("data", []) if "post" in d]
    # Posts whose only media was archived are dropped entirely.
    assert "BREAKING: Fire on campus" not in bodies
    assert "LOOK: Long lines today" not in bodies
    # Posts with surviving media remain.
    assert "Look at these cute dogs" in bodies  # u02 kept
    assert "UPDATE: schedule changed" in bodies  # a01 kept (non-special album)


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
