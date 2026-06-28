from pathlib import Path

from PIL import Image

from streamlinify.thumbnails.service import ThumbnailService


def _make_image(path: Path, w: int, h: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), (10, 80, 160)).save(path, "JPEG")


def test_generates_bounded_thumbnail(tmp_path: Path):
    src = tmp_path / "src" / "big.jpg"
    _make_image(src, 400, 200)
    svc = ThumbnailService(cache_dir=tmp_path / "cache", size=64)

    out = svc.thumbnail_path("big", src)
    assert out.exists()
    with Image.open(out) as im:
        assert max(im.size) <= 64


def test_caches_second_call(tmp_path: Path):
    src = tmp_path / "src" / "big.jpg"
    _make_image(src, 400, 200)
    svc = ThumbnailService(cache_dir=tmp_path / "cache", size=64)

    out1 = svc.thumbnail_path("big", src)
    mtime = out1.stat().st_mtime_ns
    out2 = svc.thumbnail_path("big", src)
    assert out2 == out1
    assert out2.stat().st_mtime_ns == mtime  # not regenerated
