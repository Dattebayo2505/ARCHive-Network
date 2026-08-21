"""Filesystem helpers shared by the routers.

Windows holds locks on files that are open elsewhere (Explorer preview panes, an
antivirus scan, a still-draining thumbnail request), so a single ``rmtree`` can
silently leave a half-deleted tree behind. Every delete in this app goes through
``remove_tree``, which retries and — crucially — *verifies* the directory is gone
instead of trusting ``ignore_errors=True``.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import time
from pathlib import Path


def _handle_readonly(func, path, exc_or_info):
    """Clear read-only attribute (chmod u+w) and retry unlinking."""
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        func(path)
    except OSError:
        pass


def remove_tree(path: Path, attempts: int = 5) -> bool:
    """Delete a directory tree, tolerating Windows file locks and read-only files. Returns True iff gone."""
    for _ in range(attempts):
        if not path.exists():
            return True
        try:
            if sys.version_info >= (3, 12):
                shutil.rmtree(path, onexc=_handle_readonly)
            else:
                shutil.rmtree(path, onerror=_handle_readonly)
        except OSError:
            pass
        if not path.exists():
            return True
        time.sleep(0.2)
    return not path.exists()
