from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path
from typing import Protocol

import boto3
from botocore.exceptions import ClientError

UNCATEGORIZED = "uncategorized"


def media_key(fbid: str, hashtag: str | None, group: str, suffix: str) -> str:
    """The object-store key for one media file.

    Grouped by the album's **canonical hashtag**, then by the album (or the literal
    `videos` / `unanchored` group), and named by the **fbid**:

        fb-exports/archevt/animusika-2026/1470662168409180.jpg

    The hashtag and the album name are mutable in principle, so this key is NOT
    self-healing the way the old date/fbid key was. What makes it safe is the freeze in
    `load.py`: `storage_path` is absent from the UPSERT's UPDATE set and `load()` reuses
    any key already on the row, so a renamed album yields a *stale-but-valid* key rather
    than a stranded object. Do not remove the freeze.

    Media with no canonical tag lands in `uncategorized/` — a deliberate, visible bucket,
    never a guess.
    """
    tag = (hashtag or UNCATEGORIZED).lower()
    return f"fb-exports/{tag}/{group}/{fbid}{suffix}"


class Storage(Protocol):
    """The object store.

    `LocalStorage` for dev; an `S3Storage` drops in unchanged later — both compute the *same*
    key, so only the base URL used to render it differs. The DB stores the key, never the domain.
    """

    def key_for(self, fbid: str, hashtag: str | None, group: str, suffix: str) -> str: ...
    def exists(self, key: str) -> bool: ...
    def put(self, src: Path, key: str) -> bool: ...
    def ensure_ready(self) -> None: ...


class LocalStorage:
    """Dev backend: mirror the object store on disk under `root`, served over HTTP at /store."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def key_for(self, fbid: str, hashtag: str | None, group: str, suffix: str) -> str:
        return media_key(fbid, hashtag, group, suffix)

    def exists(self, key: str) -> bool:
        return (self.root / key).exists()

    def put(self, src: Path, key: str) -> bool:
        """Copy `src` to `key`. Returns False if the key already exists (idempotent)."""
        dst = self.root / key
        if dst.exists():
            return False
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True

    def ensure_ready(self) -> None:
        """No-op preflight for the local store beyond making sure the root exists."""
        self.root.mkdir(parents=True, exist_ok=True)


class S3Storage:
    """AWS S3 backend. Computes the SAME key as LocalStorage — only the destination
    differs, so the DB/store stays backend-agnostic. `client` is injectable for tests."""

    def __init__(
        self,
        bucket: str,
        region: str,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        client=None,
    ) -> None:
        self.bucket = bucket
        if client is not None:
            self.client = client
        else:
            kwargs = {"region_name": region}
            # Pass explicit creds only when both are set; otherwise boto3's default
            # credential chain (env / ~/.aws / SSO / instance role) resolves them.
            if access_key_id and secret_access_key:
                kwargs["aws_access_key_id"] = access_key_id
                kwargs["aws_secret_access_key"] = secret_access_key
            self.client = boto3.client("s3", **kwargs)

    def key_for(self, fbid: str, hashtag: str | None, group: str, suffix: str) -> str:
        return media_key(fbid, hashtag, group, suffix)

    def ensure_ready(self) -> None:
        """Preflight: fail fast on a whole-run blocker (bad creds, missing bucket,
        no network) before we touch a single file."""
        self.client.head_bucket(Bucket=self.bucket)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def put(self, src: Path, key: str) -> bool:
        """Upload `src` to `key`. Returns False if the object already exists (idempotent)."""
        if self.exists(key):
            return False
        ctype = mimetypes.guess_type(key)[0] or "application/octet-stream"
        self.client.upload_file(str(src), self.bucket, key, ExtraArgs={"ContentType": ctype})
        return True
