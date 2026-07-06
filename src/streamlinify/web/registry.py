from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ..inventory.naming import display_name


@dataclass
class WorkspaceEntry:
    id: str
    export_root: str
    display_name: str
    managed: bool
    created_ts: float
    last_opened_ts: float


class WorkspaceRegistry:
    """Persisted list of known workspaces in ``workspace/workspaces.json``.

    Timestamps are supplied by the caller (the route layer passes ``time.time()``)
    so this module has no wall-clock dependency and stays trivially testable.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._entries: dict[str, WorkspaceEntry] = {}
        self._last_active: str | None = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        self._last_active = data.get("last_active")
        for raw in data.get("workspaces", []):
            entry = WorkspaceEntry(**raw)
            self._entries[entry.id] = entry

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "last_active": self._last_active,
            "workspaces": [asdict(e) for e in self._entries.values()],
        }
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def list(self) -> list[WorkspaceEntry]:
        return sorted(self._entries.values(), key=lambda e: e.last_opened_ts, reverse=True)

    def get(self, ws_id: str) -> WorkspaceEntry | None:
        return self._entries.get(ws_id)

    def register(
        self, export_root: Path, *, managed: bool, now: float, ws_id: str | None = None
    ) -> WorkspaceEntry:
        # ``ws_id`` lets the caller name the workspace from something other than the
        # export folder — e.g. the original zip filename, which carries the friendly
        # ``facebook-<page>-<date>-<suffix>`` pattern the extracted root often lacks.
        ws_id = ws_id or export_root.name
        entry = self._entries.get(ws_id)
        if entry is None:
            entry = WorkspaceEntry(
                id=ws_id,
                export_root=str(export_root),
                display_name=display_name(ws_id),
                managed=managed,
                created_ts=now,
                last_opened_ts=now,
            )
            self._entries[ws_id] = entry
        else:
            entry.export_root = str(export_root)
            entry.managed = managed
            entry.last_opened_ts = now
        self._last_active = ws_id
        self._save()
        return entry

    def remove(self, ws_id: str) -> WorkspaceEntry | None:
        entry = self._entries.pop(ws_id, None)
        if entry is not None:
            if self._last_active == ws_id:
                self._last_active = None
            self._save()
        return entry

    @property
    def last_active(self) -> str | None:
        return self._last_active
