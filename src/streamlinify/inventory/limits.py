import json
from pathlib import Path

class LimitState:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._limits: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._limits = dict(data)
            except Exception:
                pass

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._limits, indent=2), encoding="utf-8")

    def get_limit(self, album_fbid: str, default: int) -> int:
        return self._limits.get(album_fbid, default)

    def set_limit(self, album_fbid: str, limit: int) -> None:
        self._limits[album_fbid] = limit
        self._save()

    def remove_limit(self, album_fbid: str) -> None:
        if album_fbid in self._limits:
            del self._limits[album_fbid]
            self._save()
