import json
from datetime import datetime, timezone
from pathlib import Path

from archivenetwork.loader.read import read_ready


def test_reads_albums_and_media_from_the_ready_folder_alone(ready_root: Path):
    r = read_ready(ready_root)

    # grouping fixture: derived caption-albums (g01, g03) + one named FB album (111)
    by_id = {a.fb_album_id: a for a in r.albums}
    assert "g01" in by_id and "111" in by_id

    # a derived caption-album: synthetic id, headline title, is_derived True
    assert by_id["g01"].title == "HEADLINE ONE"
    assert by_id["g01"].is_derived is True

    # a named FB album: real FB id from the PATH (not the "1.json" filename), is_derived False
    assert by_id["111"].is_derived is False


def test_album_id_comes_from_the_path_and_unanchored_media_is_null(ready_root: Path):
    media = {m.fbid: m for m in read_ready(ready_root).media}

    assert media["g01"].fb_album_id == "g01"  # derived album, path-derived synthetic id
    assert media["a01"].fb_album_id == "111"  # named FB album
    assert media["s01"].fb_album_id is None  # loose singleton -> unanchored


def test_caption_is_hoisted_from_the_post_body(ready_root: Path):
    media = {m.fbid: m for m in read_ready(ready_root).media}
    assert media["g01"].caption == "HEADLINE ONE\n\nBody one."


def test_creation_at_is_set_and_utc_aware(ready_root: Path):
    media = {m.fbid: m for m in read_ready(ready_root).media}
    assert media["g01"].creation_at is not None
    assert media["g01"].creation_at.tzinfo is not None


def test_creation_at_prefers_the_post_timestamp_over_the_album(tmp_path: Path):
    """COALESCE(post.timestamp, album.creation_timestamp) — the post wins when both exist.

    Hand-built rather than using `ready_root`: the shared grouping fixture's posts carry no
    top-level `timestamp`, so it can only exercise the album fallback, never the preference.
    """
    posts = tmp_path / "posts"
    (posts / "album").mkdir(parents=True)
    (posts / "media" / "Album_777").mkdir(parents=True)
    (posts / "media" / "Album_777" / "p01.jpg").write_bytes(b"\xff\xd8\xff\xdbJPEG")

    album_ts, post_ts = 1_700_000_000, 1_700_086_400  # a day apart
    (posts / "album" / "0.json").write_text(
        json.dumps(
            {
                "name": "Album",
                "photos": [
                    {
                        "uri": "posts/media/Album_777/p01.jpg",
                        "creation_timestamp": album_ts,
                        "title": "T",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (posts / "profile_posts_1.json").write_text(
        json.dumps(
            [
                {
                    "timestamp": post_ts,
                    "data": [{"post": "Body"}],
                    "attachments": [
                        {"data": [{"media": {"uri": "posts/media/Album_777/p01.jpg"}}]}
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    media = {m.fbid: m for m in read_ready(tmp_path).media}
    assert media["p01"].creation_at == datetime.fromtimestamp(post_ts, tz=timezone.utc)


def test_never_posted_unanchored_media_is_still_read(ready_root: Path):
    """`n01` has no caption and no post — it is reachable only via posts/unanchored.json."""
    media = {m.fbid: m for m in read_ready(ready_root).media}

    assert "n01" in media
    assert media["n01"].fb_album_id is None  # belongs to no album
    assert media["n01"].caption is None  # never posted -> no body to hoist
    assert media["n01"].uri == "posts/media/n01.jpg"


def test_unanchored_manifest_does_not_clobber_a_feed_caption(ready_root: Path):
    """`s01` is in BOTH the feed and unanchored.json; the feed's caption must survive."""
    media = {m.fbid: m for m in read_ready(ready_root).media}
    assert media["s01"].caption == "Solo headline\n\nSolo body."


def test_archived_media_never_appears(ready_root: Path):
    fbids = {m.fbid for m in read_ready(ready_root).media}
    assert "t01" not in fbids  # BREAKING: news-tagged -> archived out by the builder


def test_every_uri_is_prefix_stripped(ready_root: Path):
    assert all(m.uri.startswith("posts/") for m in read_ready(ready_root).media)


def test_captions_reach_the_rows_with_hashtags_stripped(ready_root: Path):
    data = read_ready(ready_root)
    g01 = next(m for m in data.media if m.fbid == "g01")
    assert g01.caption == "HEADLINE ONE\n\nBody one."
    assert "#" not in g01.caption


def test_album_hashtag_is_derived_from_its_photos_captions(ready_root: Path):
    data = read_ready(ready_root)
    by_title = {a.title: a for a in data.albums}
    assert by_title["HEADLINE ONE"].hashtag == "ARCHEVT"
    assert by_title["HEADLINE TWO"].hashtag == "ARCHSPORTS"
    assert by_title["Animo Fest"].hashtag == "ARCHEVT"


def test_media_inherits_its_albums_hashtag_and_slug_group(ready_root: Path):
    data = read_ready(ready_root)
    g01 = next(m for m in data.media if m.fbid == "g01")
    assert g01.hashtag == "ARCHEVT"
    assert g01.group == "headline-one"


def test_unanchored_media_has_no_tag_and_the_unanchored_group(ready_root: Path):
    data = read_ready(ready_root)
    s01 = next(m for m in data.media if m.fbid == "s01")
    assert s01.fb_album_id is None
    assert s01.hashtag is None
    assert s01.group == "unanchored"
