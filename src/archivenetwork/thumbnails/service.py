from __future__ import annotations

from pathlib import Path

from PIL import Image

from ..config import settings


class ThumbnailService:
    def __init__(self, cache_dir: Path, size: int | None = None) -> None:
        self.cache_dir = cache_dir
        self.size = size or settings.thumb_size
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def thumbnail_path(self, fbid: str, source: Path) -> Path:
        out = self.cache_dir / f"{fbid}_{self.size}.jpg"
        if out.exists():
            return out
        with Image.open(source) as im:
            im = im.convert("RGB")
            im.thumbnail((self.size, self.size))
            im.save(out, "JPEG", quality=80)
        return out
