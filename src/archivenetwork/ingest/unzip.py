from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from ..config import settings

# 7-Zip CLI names to probe on PATH when no explicit/vendored binary is usable.
# 7zz = the official 7-Zip build for macOS/Linux; 7z / 7za = p7zip.
_SEVEN_ZIP_NAMES = ("7zz", "7z", "7za")


def find_seven_zip() -> Path | None:
    """Locate a usable 7-Zip binary, or return None to signal a zipfile fallback.

    Preference: the explicit/vendored path from settings (used as-is when it
    exists), then a 7-Zip on PATH. The committed vendored binary is a *Windows*
    build, so a ``.exe`` is only trusted on Windows — on macOS/Linux we skip
    straight to PATH discovery and, failing that, Python's zipfile.
    """
    exe = settings.seven_zip_exe
    if exe is not None:
        exe = Path(exe)
        if exe.exists() and (sys.platform.startswith("win") or exe.suffix.lower() != ".exe"):
            return exe
    for name in _SEVEN_ZIP_NAMES:
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def extract_zip(zip_path: Path, dest: Path) -> Path:
    """Extract `zip_path` into `dest`.

    Uses a 7-Zip binary when one is available (far faster than Python's `zipfile`
    on the large FB export); otherwise falls back to the stdlib `zipfile` so the
    tool still works on machines without 7-Zip installed. Either way we first scan
    the archive's central directory with `zipfile` — that reads only the entry
    names (no decompression, effectively instant) — to reject zip-slip paths
    before anything touches the disk.
    """
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()

    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            target = (dest / member).resolve()
            if dest_resolved not in target.parents and target != dest_resolved:
                raise ValueError(f"Unsafe path in zip (zip-slip): {member}")

    exe = find_seven_zip()
    if exe is not None:
        # x = extract with full paths, -o = output dir, -y = assume yes,
        # -bso0/-bse0/-bsp0 = silence stdout/stderr/progress streams.
        subprocess.run(
            [str(exe), "x", str(zip_path), f"-o{dest}", "-y", "-bso0", "-bse0", "-bsp0"],
            check=True,
        )
    else:
        # No 7-Zip on this machine: stdlib fallback (slower, but zero-dependency
        # and cross-platform). The zip-slip scan above already vetted the paths.
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(dest)
    return dest
