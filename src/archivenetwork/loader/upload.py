"""Push a built ready folder's media to an object store, on demand.

Deliberately DB-free: keys are pure-recompute via ``storage.key_for`` (never read from
Postgres). Storage is written; nothing is inserted. Mirrors ``load()``'s resilient
per-file philosophy (an orphan uri or one bad file never sinks the run), but the preflight
``ensure_ready`` fails fast on a whole-run blocker so we don't hammer every file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

from .read import read_ready
from .storage import Storage


@dataclass
class UploadResult:
    uploaded: int = 0
    skipped: int = 0
    orphans: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def upload_ready(ready_root: Path, storage: Storage) -> UploadResult:
    # Preflight: a whole-run blocker (bad creds, missing bucket, no network) raises here,
    # before the per-file loop. The route maps it to a 502.
    storage.ensure_ready()

    data = read_ready(ready_root)
    result = UploadResult()
    for row in data.media:
        src = ready_root / row.uri
        if not src.exists():
            result.orphans.append(row.uri)  # a uri with no file — reported, never uploaded
            continue
        key = storage.key_for(row.fbid, row.hashtag, row.group, src.suffix)
        try:
            if storage.put(src, key):
                result.uploaded += 1
            else:
                result.skipped += 1
        except (OSError, ClientError, BotoCoreError) as exc:
            result.errors.append(f"{row.fbid}: {exc}")
    return result
