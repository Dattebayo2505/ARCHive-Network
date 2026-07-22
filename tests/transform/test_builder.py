import json
from pathlib import Path

from archivenetwork.transform.builder import build_ready_folder


def test_build_filtered_mirror(export_root: Path, tmp_path: Path):
    dest = tmp_path / "ready"
    # A stale keep set that names 2 album-111 photos AND both non-album photos.
    keep = {"a01", "a02", "m01", "m02"}
    result = build_ready_folder(export_root, dest, keep)

    # album 0 rewritten to exactly the 2 kept photos
    album0 = json.loads((dest / "posts" / "album" / "0.json").read_text(encoding="utf-8"))
    assert {Path(p["uri"]).stem for p in album0["photos"]} == {"a01", "a02"}

    # album 1 had 0 kept photos → not written
    assert not (dest / "posts" / "album" / "1.json").exists()

    # media copied for present files only
    assert (dest / "posts" / "media" / "AnimoFest_111" / "a01.jpg").exists()
    # m01/m02 belong to no album: disregarded, never copied even though `keep` names them
    # and m01's file exists. They are subtracted before the on-disk check, so the orphan
    # m02 is not even reported — it was never a build candidate.
    assert not (dest / "posts" / "media" / "Mobileuploads_999" / "m01.jpg").exists()
    assert not (dest / "posts" / "media" / "Mobileuploads_999" / "m02.jpg").exists()
    assert result.copied == 2
    assert result.orphans == []
    assert result.non_album_skipped == 2

    # no video still was captured in this build → no videos.json manifest
    assert not (dest / "posts" / "videos.json").exists()

    # profile_posts filtered to kept + present media; the mobile-dump post loses both its
    # attachments and is dropped entirely.
    posts = json.loads((dest / "posts" / "profile_posts_1.json").read_text(encoding="utf-8"))
    kept_uris = {
        Path(d["media"]["uri"]).stem
        for post in posts
        for att in post.get("attachments", [])
        for d in att.get("data", [])
    }
    assert kept_uris == {"a01", "a02"}

    # original untouched
    assert (export_root / "posts" / "videos.json").exists()


def test_orphan_album_media_is_reported(export_root: Path, tmp_path: Path):
    """A kept album photo whose file is missing is reported, not silently dropped.

    Lives apart from `test_build_filtered_mirror` because that fixture's only orphan
    (`m02`) is a non-album photo, which is now disregarded before the disk check.
    """
    (export_root / "posts" / "media" / "AnimoFest_111" / "a03.jpg").unlink()
    result = build_ready_folder(export_root, tmp_path / "ready", {"a01", "a03"})

    assert result.copied == 1
    assert [o for o in result.orphans if "a03" in o]


def test_nothing_is_auto_kept(grouping_export_root: Path, tmp_path: Path):
    """An empty selection must build an empty folder — no photo, video or album ships
    unless the user picked it. Guards against auto-keep creeping back in."""
    dest = tmp_path / "ready"
    result = build_ready_folder(grouping_export_root, dest, keep_fbids=set())

    assert result.copied == 0
    assert result.videos_built == 0
    assert result.albums_written == 0
    assert not (dest / "posts" / "album").exists()
    assert not any((dest / "posts" / "media").rglob("*.jpg"))


def test_non_album_media_is_never_built(grouping_export_root: Path, tmp_path: Path):
    """A photo belonging to no album is disregarded — never copied, never manifested.

    `s01` (a captioned singleton) and `n01` (no caption, never posted) both end up in the
    synthetic `__non_album__` bucket. The ready folder is album-keyed all the way down to
    the S3 key, so there is no slot for them; the builder drops them even when `keep` names
    them. That also retires `posts/unanchored.json`, which existed only to make such a copied
    file reachable from *some* manifest.
    """
    from archivenetwork.inventory.parser import build_inventory

    dest = tmp_path / "ready"
    inv = build_inventory(grouping_export_root)
    keep = {p.fbid for p in inv.all_photos() if p.exists}
    result = build_ready_folder(grouping_export_root, dest, keep)

    assert not (dest / "posts" / "unanchored.json").exists()
    assert not (dest / "posts" / "media" / "s01.jpg").exists()
    assert not (dest / "posts" / "media" / "n01.jpg").exists()
    assert result.non_album_skipped == 2

    # "Every copied file is reachable from a manifest" still holds — now by exclusion.
    referenced: set[str] = set()
    for ap in (dest / "posts" / "album").glob("*.json"):
        referenced |= {p["uri"] for p in json.loads(ap.read_text(encoding="utf-8"))["photos"]}
    on_disk = {
        str(p.relative_to(dest)).replace("\\", "/")
        for p in (dest / "posts" / "media").rglob("*")
        if p.is_file()
    }
    assert not (on_disk - referenced)


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
    # u02/u03/p02 survive archiving but are singletons from the special dumps, so they land
    # in `__non_album__` — disregarded, and likewise never copied.
    assert not (dest / "posts" / "media" / "u02.jpg").exists()
    # Only the named album's photo ships.
    assert (dest / "posts" / "media" / "AnimoFest_111" / "a01.jpg").exists()

    posts = json.loads((dest / "posts" / "profile_posts_1.json").read_text(encoding="utf-8"))
    bodies = [d["post"] for post in posts for d in post.get("data", []) if "post" in d]
    # Posts whose only media was archived are dropped entirely.
    assert "BREAKING: Fire on campus" not in bodies
    assert "LOOK: Long lines today" not in bodies
    # …as are posts whose only media was non-album.
    assert "Look at these cute dogs" not in bodies  # u02 disregarded
    # Posts with surviving media remain.
    assert "UPDATE: schedule changed" in bodies  # a01 kept (non-special album)


def test_build_writes_caption_albums(grouping_export_root: Path, tmp_path: Path):
    from archivenetwork.inventory.parser import build_inventory

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

    # singleton + no-caption: non-album, so disregarded — no loose media, no album JSON
    assert not (media / "s01.jpg").exists()
    assert not (media / "n01.jpg").exists()

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
    assert not any(u.endswith("posts/media/s01.jpg") for u in uris)  # non-album → dropped
    bodies = [d["post"] for post in posts for d in post.get("data", []) if "post" in d]
    assert "BREAKING: fire" not in bodies
