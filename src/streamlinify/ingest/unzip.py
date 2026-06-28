from __future__ import annotations

import zipfile
from pathlib import Path


def extract_zip(zip_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            target = (dest / member).resolve()
            if dest_resolved not in target.parents and target != dest_resolved:
                raise ValueError(f"Unsafe path in zip (zip-slip): {member}")
        zf.extractall(dest)
    return dest
