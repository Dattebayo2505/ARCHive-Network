from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..inventory.models import ExportInventory
from ..selection.state import SelectionState
from ..thumbnails.service import ThumbnailService


@dataclass
class Session:
    export_root: Path
    inventory: ExportInventory
    selection: SelectionState
    thumbnails: ThumbnailService
