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
    post_timestamp: datetime | None = None
    taken_timestamp: datetime | None = None
    album_fbid: str | None = None
    exists: bool = True  # False when the referenced file is missing on disk (orphan)
    file_size_bytes: int = 0
    archived: bool = False  # True when set aside by a news-caption tag
    archive_tag: str | None = None  # the matched keyword, e.g. "BREAKING"
    is_video: bool = False  # True when the media is a video (mp4/mov/webm), not a photo
    ready_uri: str | None = None  # dest path (from posts/) in the ready folder; None = copy in place

    @property
    def is_non_album(self) -> bool:
        return self.album_fbid is None


class Album(BaseModel):
    fb_album_id: str
    name: str
    original_name: str | None = None
    description: str | None = None
    photos: list[Photo] = []
    uncapped: bool = False  # no per-album cap: the derived caption-albums + `__non_album__`
    origin: str | None = None  # parent dump name for a derived caption-album (UI subheader)
    media_slug: str | None = None  # derived album's media subdir "<slug>_<id>"; None for FB albums
    post_timestamp: datetime | None = None


class ExportInventory(BaseModel):
    albums: list[Album] = []
    non_album_photos: list[Photo] = []
    archived_photos: list[Photo] = []
    archived_albums: list[Album] = []
    videos: list[Photo] = []

    def all_photos(self) -> list[Photo]:
        out: list[Photo] = [p for a in self.albums for p in a.photos]
        out.extend(self.non_album_photos)
        out.extend(self.archived_photos)
        out.extend([p for a in self.archived_albums for p in a.photos])
        out.extend(self.videos)
        return out

    def photo_by_fbid(self, fbid: str) -> Photo | None:
        for p in self.all_photos():
            if p.fbid == fbid:
                return p
        return None
