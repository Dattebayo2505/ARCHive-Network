from __future__ import annotations

import os
import string
import sys
from pathlib import Path

from .validate import find_export_root, validate_export


def available_roots() -> list[str]:
    """Filesystem roots the picker can jump to: drive letters on Windows, mount points on macOS/Linux."""
    if os.name == "nt":
        roots = []
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            try:
                p = Path(root)
                if p.exists() and p.is_dir():
                    roots.append(root)
            except OSError:
                continue
        return roots or [str(Path.home().anchor or "C:\\")]
    if sys.platform == "darwin":
        candidates = ["/", "/Volumes"]
        roots = []
        for c in candidates:
            try:
                p = Path(c)
                if p.exists() and p.is_dir():
                    roots.append(c)
            except OSError:
                continue
        return roots or ["/"]
    candidates = ["/", "/media", "/mnt", "/run/media"]
    user = os.environ.get("USER") or os.environ.get("LOGNAME")
    if user:
        candidates.append(f"/run/media/{user}")
    roots = []
    for path_str in candidates:
        try:
            p = Path(path_str)
            if p.exists() and p.is_dir() and path_str not in roots:
                roots.append(path_str)
        except OSError:
            continue
    return roots or ["/"]


def _is_export(folder: Path) -> bool:
    """True when ingesting `folder` would succeed (ingest descends one level)."""
    try:
        return validate_export(find_export_root(folder)).ok
    except (OSError, ValueError):
        return False


def list_directory(folder: Path | None) -> dict:
    """List the immediate sub-directories and `.zip` files of `folder`.

    Defaults to the user's home directory when `folder` is falsy. Sub-dirs feed
    folder navigation; `.zip` files let the picker load an archive in place (the
    server unzips it locally — no HTTP upload). Hidden entries (leading dot) and
    unreadable ones are skipped. Raises FileNotFoundError / NotADirectoryError
    for a bad path so the route can surface a clear 400.
    """
    base = Path(folder).expanduser() if folder else Path.home()
    if not base.exists():
        raise FileNotFoundError(str(base))
    if not base.is_dir():
        raise NotADirectoryError(str(base))
    base = base.resolve()

    dirs: list[dict] = []
    files: list[dict] = []
    try:
        children = sorted(base.iterdir(), key=lambda p: p.name.lower())
    except PermissionError:
        children = []
    for child in children:
        if child.name.startswith("."):
            continue
        try:
            if child.is_dir():
                dirs.append(
                    {"name": child.name, "path": str(child), "is_export": _is_export(child)}
                )
            elif child.is_file() and child.suffix.lower() == ".zip":
                files.append({"name": child.name, "path": str(child)})
        except OSError:
            continue

    parent = str(base.parent) if base.parent != base else None
    return {
        "path": str(base),
        "parent": parent,
        "dirs": dirs,
        "files": files,
        "is_export": _is_export(base),
        "drives": available_roots(),
    }
