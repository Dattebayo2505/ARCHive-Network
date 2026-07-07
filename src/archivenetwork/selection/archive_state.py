from __future__ import annotations

import json
from pathlib import Path


class ArchiveState:
    """Persists which albums the user has archived, in ``archive.json``.

    Mirrors ``RenameState``: a small JSON file (an array of album fbids) that
    survives reload/restart so archived albums are restored when the workspace
    is reopened. The in-memory ``inventory.archived_albums`` move is layered on
    top of this at session-build time.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._ids: set[str] = set()
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._ids = set(data)
            except (json.JSONDecodeError, OSError, TypeError):
                pass

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(sorted(self._ids), indent=2), encoding="utf-8")

    def archived_ids(self) -> set[str]:
        return set(self._ids)

    def is_archived(self, album_fbid: str) -> bool:
        return album_fbid in self._ids

    def add(self, album_fbid: str) -> None:
        if album_fbid not in self._ids:
            self._ids.add(album_fbid)
            self._save()

    def remove(self, album_fbid: str) -> None:
        if album_fbid in self._ids:
            self._ids.discard(album_fbid)
            self._save()
