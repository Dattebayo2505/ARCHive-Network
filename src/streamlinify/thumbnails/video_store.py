from __future__ import annotations

from pathlib import Path


class VideoThumbnailStore:
    """On-disk store for per-video still frames chosen in the browser.

    One file per video: <base_dir>/<fbid>.jpg. Lives under workspace/ (gitignored),
    never in the read-only export. The frame itself is captured client-side.
    """

    def __init__(self, base_dir: Path) -> None:
        self.dir = base_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def path(self, fbid: str) -> Path:
        return self.dir / f"{fbid}.jpg"

    def has(self, fbid: str) -> bool:
        return self.path(fbid).exists()

    def save(self, fbid: str, data: bytes, is_auto: bool = False) -> Path:
        target = self.path(fbid)
        target.write_bytes(data)
        applied_flag = self.dir / f"{fbid}.applied"
        if not is_auto:
            applied_flag.touch()
        else:
            applied_flag.unlink(missing_ok=True)
        return target

    def is_auto(self, fbid: str) -> bool:
        return not (self.dir / f"{fbid}.applied").exists()
