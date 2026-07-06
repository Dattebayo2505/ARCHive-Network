from __future__ import annotations

import re
from collections import OrderedDict

from .models import Album, ExportInventory, Photo

_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")


def caption_headline(caption: str) -> str:
    """The caption's first non-empty line, trimmed and truncated to 100 chars."""
    for line in caption.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:100]
    return caption.strip()[:100]


def media_slug(headline: str, synth_id: str) -> str:
    """`<AlnumHeadline≤30>_<synthId>` — the per-group media subdir name.

    The trailing `_<synthId>` mirrors FB's `<Album>_<albumFbid>` so the downstream
    ETL (and our own `album_id_from_uri`) recovers the synthetic id from the path.
    """
    alnum = _NON_ALNUM.sub("", headline)[:30] or "album"
    return f"{alnum}_{synth_id}"


def derive_caption_albums(inventory: ExportInventory) -> None:
    """Cluster the two uncapped dumps' photos by caption into real photo_albums.

    For each `uncapped` album: photos sharing a non-empty caption form a derived album
    (synthetic id = the group's first photo fbid, name = the caption headline). Groups
    of one, and any no-caption photo, become unanchored — moved to `non_album_photos`
    with a loose `ready_uri`. Non-uncapped albums pass through unchanged. Derived albums
    are appended at the end of the album list so that their subheadings do not swallow
    regular albums in the UI.
    """
    normal_albums: list[Album] = []
    derived_albums: list[Album] = []
    for album in inventory.albums:
        if not album.uncapped:
            normal_albums.append(album)
            continue

        groups: "OrderedDict[str, list[Photo]]" = OrderedDict()
        loose: list[Photo] = []
        for photo in album.photos:
            key = (photo.caption or "").strip()
            if key:
                groups.setdefault(key, []).append(photo)
            else:
                loose.append(photo)

        for key, members in groups.items():
            if len(members) < 2:
                loose.extend(members)
                continue
            synth = members[0].fbid
            headline = caption_headline(key)
            slug = media_slug(headline, synth)
            for photo in members:
                photo.album_fbid = synth
                photo.ready_uri = f"posts/media/{slug}/{photo.fbid}.jpg"
            derived_albums.append(
                Album(
                    fb_album_id=synth, name=headline, origin=album.name,
                    uncapped=True, media_slug=slug, photos=members,
                )
            )

        for photo in loose:
            photo.album_fbid = None
            photo.ready_uri = f"posts/media/{photo.fbid}.jpg"
            inventory.non_album_photos.append(photo)

    inventory.albums = normal_albums + derived_albums
