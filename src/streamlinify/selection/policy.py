from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..config import settings


class CapExceeded(Exception):
    def __init__(self, album_fbid: str) -> None:
        super().__init__(f"album {album_fbid} is at its selection cap")
        self.album_fbid = album_fbid


class SelectionPolicy(Protocol):
    def can_select(self, album_fbid: str, current_count: int) -> bool: ...
    def non_album_selectable(self) -> bool: ...


@dataclass
class DefaultPolicy:
    """Named-album cap; non-album photos are auto-kept and not pickable (Decision B).

    To make non-album photos deselectable later, add a sibling policy whose
    `non_album_selectable()` returns True — no change to SelectionState needed.
    """

    max_per_album: int = settings.max_per_album

    def can_select(self, album_fbid: str, current_count: int) -> bool:
        return current_count < self.max_per_album

    def non_album_selectable(self) -> bool:
        return False
