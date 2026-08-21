from __future__ import annotations

import os
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
    """Locate a usable 7-Zip binary, or return None to signal a native/zipfile fallback.

    Preference: the explicit/vendored path from settings (Windows ``7za.exe``, macOS
    ``7zz_mac``, Linux ``7zzs_x64``/``7zzs_x32``), then a 7-Zip on PATH. A ``.exe``
    is only trusted on Windows.
    """
    exe = settings.seven_zip_exe
    if exe is not None:
        exe = Path(exe)
        if exe.exists() and (sys.platform.startswith("win") or exe.suffix.lower() != ".exe"):
            if not sys.platform.startswith("win"):
                try:
                    if not os.access(exe, os.X_OK):
                        exe.chmod(exe.stat().st_mode | 0o755)
                except OSError:
                    pass
            return exe
    for name in _SEVEN_ZIP_NAMES:
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def extract_zip(zip_path: Path, dest: Path) -> Path:
    """Extract `zip_path` into `dest`.

    Uses a 7-Zip binary when one is available (far faster than Python's `zipfile`
    on the large FB export); otherwise checks for native platform extractors
    (`ditto` on macOS, `unzip` on Linux/POSIX); and finally falls back to the
    stdlib `zipfile` so the tool still works on machines without external tools.
    Either way we first scan the archive's central directory with `zipfile` —
    that reads only the entry names (no decompression, effectively instant) —
    to reject zip-slip paths before anything touches the disk.
    """
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()

    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            target = (dest / member).resolve()
            if dest_resolved not in target.parents and target != dest_resolved:
                raise ValueError(f"Unsafe path in zip (zip-slip): {member}")

    # 1. 7-Zip (fastest)
    exe = find_seven_zip()
    if exe is not None:
        try:
            # x = extract with full paths, -o = output dir, -y = assume yes,
            # -bso0/-bse0/-bsp0 = silence stdout/stderr/progress streams.
            subprocess.run(
                [str(exe), "x", str(zip_path), f"-o{dest}", "-y", "-bso0", "-bse0", "-bsp0"],
                check=True,
            )
            return dest
        except (subprocess.CalledProcessError, OSError):
            pass

    # 2. macOS ditto
    if sys.platform == "darwin" or shutil.which("ditto"):
        try:
            subprocess.run(
                ["ditto", "-x", "-k", str(zip_path), str(dest)],
                check=True,
            )
            return dest
        except (subprocess.CalledProcessError, OSError):
            pass

    # 3. Linux/POSIX unzip
    if unzip_bin := shutil.which("unzip"):
        try:
            subprocess.run(
                [unzip_bin, "-q", "-o", str(zip_path), "-d", str(dest)],
                check=True,
            )
            return dest
        except (subprocess.CalledProcessError, OSError):
            pass

    # 4. Python stdlib fallback (slower, but zero-dependency and cross-platform).
    # The zip-slip scan above already vetted the paths.
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    return dest

