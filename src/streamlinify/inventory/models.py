from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class Photo(BaseModel):
    fbid: str
    original_uri: str
    resolved_path: Path
    title: str | None = None
    caption: str | None = None
    creation_at: datetime | None = None
    album_fbid: str | None = None
    exists: bool = True  # False when the referenced file is missing on disk (orphan)
    archived: bool = False  # True when set aside by a news-caption tag
    archive_tag: str | None = None  # the matched keyword, e.g. "BREAKING"

    @property
    def is_non_album(self) -> bool:
        return self.album_fbid is None


class Album(BaseModel):
    fb_album_id: str
    name: str
    photos: list[Photo] = []
    uncapped: bool = False  # True for the special dump albums (no per-album cap)


class ExportInventory(BaseModel):
    albums: list[Album] = []
    non_album_photos: list[Photo] = []
    archived_photos: list[Photo] = []

    def all_photos(self) -> list[Photo]:
        out: list[Photo] = [p for a in self.albums for p in a.photos]
        out.extend(self.non_album_photos)
        out.extend(self.archived_photos)
        return out

    def photo_by_fbid(self, fbid: str) -> Photo | None:
        for p in self.all_photos():
            if p.fbid == fbid:
                return p
        return None
