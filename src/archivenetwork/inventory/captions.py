"""Per-workspace album caption overrides, persisted to `state/<id>/captions.json`.

Sibling of `RenameState` / `LimitState`: the export on disk is never touched, the override
lives beside the workspace's other decisions, and it is applied to the live inventory at
session start (`web/routes_ingest.py`) and to the album JSON at build time
(`transform/builder.py`).

Values are stored **raw** — prose plus the album's original hashtag block — so the ready
folder keeps its FB-shaped, hashtag-bearing caption. The UI only ever edits the prose;
`routes_gallery` re-attaches the tags with `hashtags.join_hashtags` before saving here.
"""

import json
from pathlib import Path


class CaptionState:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._captions: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._captions = {k: v for k, v in dict(data).items() if isinstance(v, str)}
            except Exception:
                pass

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._captions, indent=2), encoding="utf-8")

    def get_caption(self, album_fbid: str, default: str | None) -> str | None:
        return self._captions.get(album_fbid, default)

    def set_caption(self, album_fbid: str, caption: str) -> None:
        self._captions[album_fbid] = caption
        self._save()

    def remove_caption(self, album_fbid: str) -> None:
        if album_fbid in self._captions:
            del self._captions[album_fbid]
            self._save()
