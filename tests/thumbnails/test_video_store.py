from pathlib import Path

from archivenetwork.thumbnails.video_store import VideoThumbnailStore


def test_save_and_read(tmp_path: Path):
    store = VideoThumbnailStore(tmp_path / "videos")
    assert not store.has("v01")
    p = store.save("v01", b"JPEGBYTES")
    assert p == tmp_path / "videos" / "v01.jpg"
    assert store.has("v01")
    assert p.read_bytes() == b"JPEGBYTES"
