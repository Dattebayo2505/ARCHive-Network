from __future__ import annotations

import mimetypes
import shutil
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

UNCATEGORIZED = "uncategorized"

# A custom endpoint (the floci emulator) must fail fast. boto3 otherwise waits out a 60s
# default connect timeout, multiplied by its default retry count, before the route can
# render a 502 — long enough that the UI reads as hung rather than failed. `dynamo.connect`
# reuses these bounds for the same reason.
ENDPOINT_CONNECT_TIMEOUT = 3
ENDPOINT_READ_TIMEOUT = 10


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
        *,
        endpoint_url: str | None = None,
        create_if_missing: bool = False,
    ) -> None:
        self.bucket = bucket
        self.region = region
        self.create_if_missing = create_if_missing
        if client is not None:
            self.client = client
        else:
            kwargs = {"region_name": region}
            # Pass explicit creds only when both are set; otherwise boto3's default
            # credential chain (env / ~/.aws / SSO / instance role) resolves them.
            if access_key_id and secret_access_key:
                kwargs["aws_access_key_id"] = access_key_id
                kwargs["aws_secret_access_key"] = secret_access_key
            if endpoint_url:
                # Path-style is load-bearing: virtual-hosted style would resolve
                # <bucket>.127.0.0.1, which does not exist.
                kwargs["endpoint_url"] = endpoint_url
                kwargs["config"] = BotoConfig(
                    s3={"addressing_style": "path"},
                    connect_timeout=ENDPOINT_CONNECT_TIMEOUT,
                    read_timeout=ENDPOINT_READ_TIMEOUT,
                    retries={"max_attempts": 1},
                )
            self.client = boto3.client("s3", **kwargs)

    def key_for(self, fbid: str, hashtag: str | None, group: str, suffix: str) -> str:
        return media_key(fbid, hashtag, group, suffix)

    def ensure_ready(self) -> None:
        """Preflight: fail fast on a whole-run blocker (bad creds, missing bucket,
        no network) before we touch a single file.

        `create_if_missing` is set ONLY for the local floci emulator, which starts empty.
        The AWS target never sets it: a preflight that can create a production bucket is
        the opposite of a preflight.
        """
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            if not self.create_if_missing:
                raise
            code = str(exc.response.get("Error", {}).get("Code"))
            # Anything else — a 403 above all — is a real problem. Swallowing it into a
            # create attempt would turn a diagnosable credential failure into a confusing
            # second one.
            if code not in ("404", "NoSuchBucket", "NotFound"):
                raise
            self._create_bucket()

    def _create_bucket(self) -> None:
        kwargs: dict = {"Bucket": self.bucket}
        if self.region and self.region != "us-east-1":
            # S3 rejects CreateBucketConfiguration for us-east-1.
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": self.region}
        self.client.create_bucket(**kwargs)

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


# --- Endpoint liveness -------------------------------------------------------------------
# Mirrors `db.probe()`: report what we can learn cheaply, without assuming the service is up.
# Bounded on purpose — an unbounded connect blocks for the OS default (~21s per address on
# Windows), which reads as a hung UI rather than a failed check.
PROBE_TIMEOUT = 1.0


@dataclass(frozen=True)
class EndpointProbe:
    """Whether anything is listening at an object-store endpoint, right now.

    Records NO cause. A refused connection cannot distinguish "Docker is not running" from
    "Docker is up but the container was never started" from "something else owns the port".
    The judgement about the likeliest cause belongs to the message layer, which has the
    context to guess; this does not.
    """

    reachable: bool
    reason: str | None = None


def probe_endpoint(endpoint_url: str, timeout: float = PROBE_TIMEOUT) -> EndpointProbe:
    """A bounded TCP connect to the endpoint's host/port. Never raises."""
    parts = urlsplit(endpoint_url)
    host = parts.hostname
    if not host:
        return EndpointProbe(reachable=False, reason=f"malformed endpoint url: {endpoint_url!r}")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout):
            return EndpointProbe(reachable=True)
    except OSError as exc:
        return EndpointProbe(reachable=False, reason=str(exc))
