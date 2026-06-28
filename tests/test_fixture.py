from pathlib import Path


def test_fixture_shape(export_root: Path):
    assert (export_root / "posts" / "album" / "0.json").exists()
    assert (export_root / "posts" / "profile_posts_1.json").exists()
    assert (export_root / "posts" / "media" / "AnimoFest_111" / "a12.jpg").exists()
    assert not (export_root / "posts" / "media" / "Mobileuploads_999" / "m02.jpg").exists()
    assert (export_root / "posts" / "videos.json").exists()
