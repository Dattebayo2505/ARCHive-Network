from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..inventory.models import ExportInventory
from ..inventory.renames import RenameState
from ..selection.state import SelectionState
from ..thumbnails.service import ThumbnailService
from ..thumbnails.video_store import VideoThumbnailStore


@dataclass
class Session:
    export_root: Path
    inventory: ExportInventory
    selection: SelectionState
    thumbnails: ThumbnailService
    video_thumbs: VideoThumbnailStore
    renames: RenameState
