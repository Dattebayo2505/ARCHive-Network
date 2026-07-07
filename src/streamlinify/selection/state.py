from __future__ import annotations

import json
from pathlib import Path

from .policy import CapExceeded, SelectionPolicy


class SelectionState:
    def __init__(self, path: Path, policy: SelectionPolicy) -> None:
        self.path = path
        self.policy = policy
        self._selected: dict[str, set[str]] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._selected = {k: set(v) for k, v in data.items()}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {k: sorted(v) for k, v in self._selected.items() if v}
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def toggle(self, album_fbid: str, photo_fbid: str) -> bool:
        sel = self._selected.setdefault(album_fbid, set())
        if photo_fbid in sel:
            sel.remove(photo_fbid)
            self._save()
            return False
        if not self.policy.can_select(album_fbid, len(sel)):
            raise CapExceeded(album_fbid)
        sel.add(photo_fbid)
        self._save()
        return True

    def deselect_all(self, album_fbid: str) -> None:
        if album_fbid in self._selected:
            del self._selected[album_fbid]
            self._save()

    def is_selected(self, album_fbid: str, photo_fbid: str) -> bool:
        return photo_fbid in self._selected.get(album_fbid, set())

    def count(self, album_fbid: str) -> int:
        return len(self._selected.get(album_fbid, set()))

    def selected_fbids(self) -> set[str]:
        out: set[str] = set()
        for fbids in self._selected.values():
            out |= fbids
        return out
