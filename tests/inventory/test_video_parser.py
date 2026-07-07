from pathlib import Path

from archivenetwork.inventory.parser import build_inventory, is_video_uri


def test_is_video_uri_by_extension():
    assert is_video_uri("posts/media/videos/x.mp4")
    assert is_video_uri("posts/media/videos/x.MOV")
    assert not is_video_uri("posts/media/AnimoFest_111/a01.jpg")


def test_videos_split_out_of_non_album(video_export_root: Path):
    inv = build_inventory(video_export_root)
    assert {v.fbid for v in inv.videos} == {"v01"}
    assert all(v.is_video for v in inv.videos)
    # the video must NOT leak into the auto-kept non-album bucket
    assert "v01" not in {p.fbid for p in inv.non_album_photos}
    # caption comes from the post body
    assert inv.videos[0].caption == "Watch this clip #ARCH"
    # a photo is still a photo
    assert any(not p.is_video for p in inv.all_photos())
