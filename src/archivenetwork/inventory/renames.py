import json
from pathlib import Path

class RenameState:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._renames: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._renames = dict(data)
            except Exception:
                pass

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._renames, indent=2), encoding="utf-8")

    def get_name(self, album_fbid: str, default: str) -> str:
        return self._renames.get(album_fbid, default)

    def set_name(self, album_fbid: str, name: str) -> None:
        self._renames[album_fbid] = name
        self._save()

    def remove_name(self, album_fbid: str) -> None:
        if album_fbid in self._renames:
            del self._renames[album_fbid]
            self._save()
