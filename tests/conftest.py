import json
from pathlib import Path

import pytest
from PIL import Image

PREFIX = "this_profile's_activity_across_facebook"


def _img(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), (120, 30, 30)).save(path, "JPEG")


def _photo_record(album_dir: str, fbid: str, title: str) -> dict:
    return {
        "uri": f"{PREFIX}/posts/media/{album_dir}/{fbid}.jpg",
        "creation_timestamp": 1_700_000_000,
        "title": title,
    }


@pytest.fixture
def export_root(tmp_path: Path) -> Path:
    root = tmp_path / "export"
    media = root / "posts" / "media"
    album_dir = root / "posts" / "album"
    album_dir.mkdir(parents=True)

    # Album 111 "Animo Fest": 12 photos, all files present
    a_photos = [_photo_record("AnimoFest_111", f"a{n:02d}", f"Photo {n}") for n in range(1, 13)]
    (album_dir / "0.json").write_text(
        json.dumps({"name": "Animo Fest", "photos": a_photos}), encoding="utf-8"
    )
    for n in range(1, 13):
        _img(media / "AnimoFest_111" / f"a{n:02d}.jpg")

    # Album 222 "Café Night" stored as mojibake; 2 photos
    b_photos = [_photo_record("CafeNight_222", f"b{n:02d}", f"B {n}") for n in range(1, 3)]
    (album_dir / "1.json").write_text(
        json.dumps({"name": "CafÃ© Night", "photos": b_photos}), encoding="utf-8"
    )
    for n in range(1, 3):
        _img(media / "CafeNight_222" / f"b{n:02d}.jpg")

    # profile_posts: post1 captions a01/a02; post2 references non-album m01 (present) + m02 (orphan)
    posts = [
        {
            "data": [{"post": "Great game today! #ARCH #Animo"}],
            "attachments": [
                {"data": [{"media": _photo_record("AnimoFest_111", "a01", "Photo 1")}]},
                {"data": [{"media": _photo_record("AnimoFest_111", "a02", "Photo 2")}]},
            ],
        },
        {
            "data": [{"post": "Mobile dump #Random"}],
            "attachments": [
                {"data": [{"media": _photo_record("Mobileuploads_999", "m01", "Mobile 1")}]},
                {"data": [{"media": _photo_record("Mobileuploads_999", "m02", "Mobile 2")}]},
            ],
        },
    ]
    (root / "posts" / "profile_posts_1.json").write_text(
        json.dumps(posts), encoding="utf-8"
    )
    _img(media / "Mobileuploads_999" / "m01.jpg")
    # NOTE: m02.jpg deliberately NOT created → orphan

    # Unnecessary JSONs that must be dropped from the ready output
    for name in (
        "videos.json",
        "content_sharing_links_you_have_created.json",
        "edits_you_made_to_posts.json",
        "places_you_have_been_tagged_in.json",
    ):
        (root / "posts" / name).write_text("[]", encoding="utf-8")

    return root
