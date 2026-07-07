"""Open the host OS file manager focused on a path.

ARCHive Network runs locally, so the same machine that serves the API also owns the
desktop. "Show in File Explorer" lets a volunteer jump from a photo (or an album)
straight to the real file on disk to sanity-check it. This only ever *opens* a
window — it never reads or writes the export, so the read-only-original promise
holds.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


class RevealError(RuntimeError):
    """The OS file manager could not be opened for the given path."""


def reveal_command(path: Path, *, platform: str | None = None) -> list[str]:
    """Build the argv that opens the file manager focused on ``path``.

    A file is *selected* (highlighted) inside its folder; a directory is opened
    directly. Linux file managers have no portable "select a file" flag, so we
    open the containing directory instead.
    """
    plat = platform or sys.platform
    if plat.startswith("win"):
        if path.is_dir():
            return ["explorer", str(path)]
        return ["explorer", f"/select,{path}"]
    if plat == "darwin":
        if path.is_dir():
            return ["open", str(path)]
        return ["open", "-R", str(path)]
    folder = path if path.is_dir() else path.parent
    return ["xdg-open", str(folder)]


def reveal_path(path: Path) -> None:
    """Open the file manager on ``path``. Raises :class:`RevealError` on failure."""
    path = Path(path)
    if not path.exists():
        raise RevealError(f"Path does not exist: {path}")
    try:
        # explorer.exe exits non-zero even on success, so we never check the code.
        if sys.platform.startswith("win") and not path.is_dir():
            # explorer.exe /select, requires non-standard quoting: the
            # /select, flag must stay unquoted and only the path after the
            # comma gets quoted.  Both subprocess with a list (adds quotes
            # around the whole arg) and list2cmdline produce the wrong form
            # — causing explorer to silently fall back to %USERPROFILE%\Documents.
            subprocess.run(f'explorer /select,"{path}"', check=False)
        else:
            subprocess.run(reveal_command(path), check=False)
    except OSError as exc:
        raise RevealError(str(exc)) from exc
