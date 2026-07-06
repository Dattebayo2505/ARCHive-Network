from __future__ import annotations

import re

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Insert a space between a lowercase/digit and a following uppercase letter.
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def display_name(export_name: str) -> str:
    """Turn an FB export folder name into a friendly label.

    ``facebook-ArchersNetwork-2026-07-03-7xOuGnNl`` ->
    ``Archers Network Facebook Export | 2026-07-03``.

    Rule: strip a leading ``facebook-``; find the first YYYY-MM-DD date; the page
    name is everything before it (CamelCase-split, ``-``/``_`` collapsed to spaces);
    everything after the date (random suffix, ``_annotation``) is dropped. If no
    date is present, return the raw name unchanged.
    """
    name = export_name
    if name.startswith("facebook-"):
        name = name[len("facebook-"):]

    match = _DATE.search(name)
    if match is None:
        return export_name

    page_raw = name[: match.start()].strip("-_ ")
    date = match.group(0)
    page = _CAMEL.sub(" ", page_raw)
    page = re.sub(r"[-_\s]+", " ", page).strip()
    return f"{page} Facebook Export | {date}"
