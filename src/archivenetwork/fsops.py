"""Filesystem helpers shared by the routers.

Windows holds locks on files that are open elsewhere (Explorer preview panes, an
antivirus scan, a still-draining thumbnail request), so a single ``rmtree`` can
silently leave a half-deleted tree behind. Every delete in this app goes through
``remove_tree``, which retries and — crucially — *verifies* the directory is gone
instead of trusting ``ignore_errors=True``.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path


def remove_tree(path: Path, attempts: int = 5) -> bool:
    """Delete a directory tree, tolerating Windows file locks. Returns True iff gone."""
    for _ in range(attempts):
        if not path.exists():
            return True
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return True
        time.sleep(0.2)
    return not path.exists()
