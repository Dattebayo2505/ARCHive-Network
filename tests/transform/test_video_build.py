import json
from pathlib import Path

from streamlinify.transform.builder import build_ready_folder


def test_video_still_replaces_mp4(video_export_root: Path, tmp_path: Path):
    thumbs = tmp_path / "vthumbs"
    thumbs.mkdir()
    (thumbs / "v01.jpg").write_bytes(b"CHOSENFRAME")

    dest = tmp_path / "ready"
    result = build_ready_folder(video_export_root, dest, keep_fbids={"v01"}, video_thumb_dir=thumbs)

    # the .jpg is written in the video's slot; the .mp4 is NOT copied
    assert (dest / "posts" / "media" / "videos" / "v01.jpg").read_bytes() == b"CHOSENFRAME"
    assert not (dest / "posts" / "media" / "videos" / "v01.mp4").exists()
    assert result.videos_built == 1 and result.skipped_videos == []

    # the rebuilt feed references the .jpg, not the .mp4
    posts = json.loads((dest / "posts" / "profile_posts_1.json").read_text(encoding="utf-8"))
    uris = [d["media"]["uri"] for p in posts for att in p["attachments"] for d in att["data"] if "media" in d]
    assert any(u.endswith("videos/v01.jpg") for u in uris)
    assert not any(u.endswith(".mp4") for u in uris)


def test_video_without_still_is_skipped(video_export_root: Path, tmp_path: Path):
    dest = tmp_path / "ready"
    result = build_ready_folder(video_export_root, dest, keep_fbids={"v01"}, video_thumb_dir=tmp_path / "empty")

    assert result.videos_built == 0
    assert any("v01.mp4" in s for s in result.skipped_videos)
    assert not (dest / "posts" / "media" / "videos" / "v01.jpg").exists()
    assert not (dest / "posts" / "media" / "videos" / "v01.mp4").exists()
    # the skipped video is dropped from the feed
    posts = json.loads((dest / "posts" / "profile_posts_1.json").read_text(encoding="utf-8"))
    uris = [d["media"]["uri"] for p in posts for att in p["attachments"] for d in att["data"] if "media" in d]
    assert not any("v01" in u for u in uris)
