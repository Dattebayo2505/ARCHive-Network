from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

from ..config import settings


def extract_zip(zip_path: Path, dest: Path) -> Path:
    """Extract `zip_path` into `dest` using the vendored 7-Zip binary.

    7zr decompresses the large FB export far faster than Python's `zipfile`. We
    still scan the archive's central directory with `zipfile` first — that reads
    only the entry names (no decompression, effectively instant) — to reject
    zip-slip paths before letting 7zr touch the disk.
    """
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()

    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            target = (dest / member).resolve()
            if dest_resolved not in target.parents and target != dest_resolved:
                raise ValueError(f"Unsafe path in zip (zip-slip): {member}")

    exe = settings.seven_zip_exe
    if not exe.exists():
        raise FileNotFoundError(f"7-Zip binary not found at {exe}")

    # x = extract with full paths, -o = output dir, -y = assume yes,
    # -bso0/-bse0/-bsp0 = silence stdout/stderr/progress streams.
    subprocess.run(
        [str(exe), "x", str(zip_path), f"-o{dest}", "-y", "-bso0", "-bse0", "-bsp0"],
        check=True,
    )
    return dest
