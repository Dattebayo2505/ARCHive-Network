"""One Publish: preflight -> `load()` into the env's bucket and tables -> a run-scoped verify.

Nothing is written unless every preflight check passes. The verify is scoped to *this run*, not
the whole table: the tables accumulate other workspaces and CMS edits, and the full `validate`
stays a separate tool. `ok` is true only when preflight passed, no file failed and every verify
check passed; orphans are listed but don't fail it (they are a build problem).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

from . import dynamo
from .envs import Env
from .load import LoadResult, load
from .read import read_ready
from .storage import S3Storage
from .validate import Check

SAMPLE = 5  # ids named in a check's detail


@dataclass
class PublishResult:
    env: str
    kind: str
    identity: str
    bucket: str
    table_prefix: str
    workspace_id: str
    ok: bool
    preflight: list[Check]
    publish: LoadResult | None
    verify: list[Check] | None

    def as_dict(self) -> dict:
        def checks(cs: list[Check] | None) -> dict | None:
            if cs is None:
                return None
            return {"ok": all(c.ok for c in cs), "checks": [asdict(c) for c in cs]}

        loaded = None
        if self.publish is not None:
            loaded = {"ok": not self.publish.errors, **asdict(self.publish)}
        return {
            "env": self.env,
            "kind": self.kind,
            "identity": self.identity,
            "bucket": self.bucket,
            "table_prefix": self.table_prefix,
            "workspace_id": self.workspace_id,
            "ok": self.ok,
            "steps": {
                "preflight": checks(self.preflight),
                "publish": loaded,
                "verify": checks(self.verify),
            },
        }


def preflight(
    env: Env, storage: S3Storage, tables: dynamo.Tables, identity: tuple[str, str]
) -> list[Check]:
    arn, account = identity
    checks = [Check("signed in", bool(arn), arn)]
    if env.kind == "aws" and env.sso is not None:
        # Catches a profile or role pointing at another account than the env names.
        expected = env.sso.account_id
        checks.append(Check(
            "account matches environment",
            account == expected,
            "" if account == expected else f"signed in to account {account}, env expects {expected}",
        ))
    try:
        storage.ensure_ready()
        checks.append(Check("bucket reachable", True, f"s3://{storage.bucket}"))
    except (ClientError, BotoCoreError) as exc:
        checks.append(Check("bucket reachable", False, f"s3://{storage.bucket}: {exc}"))

    p = dynamo.probe(tables)
    if not p.endpoint_reachable:
        detail = f"Can't reach DynamoDB at {p.endpoint} — {p.reason}"
    elif p.refused:
        detail = f"DynamoDB refused the request — {p.reason}"
    elif p.missing:
        detail = "Missing tables: " + ", ".join(p.tables[k] for k in p.missing)
    else:
        detail = f"{p.prefix}-*"
    checks.append(Check("tables ready", p.table_exists, detail))
    return checks


def _sample(ids: list[str]) -> str:
    return f"{ids[:SAMPLE]}" + (f" and {len(ids) - SAMPLE} more" if len(ids) > SAMPLE else "")


def verify(
    ready_root: Path, result: LoadResult, storage: S3Storage, tables: dynamo.Tables
) -> list[Check]:
    data = read_ready(ready_root)
    orphans = set(result.orphans)
    skipped = set(result.skipped_deleted)
    failed = set(result.failed)
    published = [
        m for m in data.media
        if m.uri not in orphans and f"media:{m.fbid}" not in skipped and m.fbid not in failed
    ]
    albums = [a for a in data.albums if f"album:{a.fb_album_id}" not in skipped]
    found = dynamo.prefetch(
        tables,
        [("media", m.fbid) for m in published] + [("album", a.fb_album_id) for a in albums],
    )

    checks: list[Check] = []
    absent = [
        m.fbid for m in published
        if not (found.get(("media", m.fbid)) and found[("media", m.fbid)].storage_path)
    ]
    checks.append(Check(
        "every published media item is in the table",
        not absent,
        f"{len(published) - len(absent)} of {len(published)} present"
        + (f"; missing: {_sample(absent)}" if absent else ""),
    ))

    missing: list[str] = []
    differs: list[str] = []
    for m in published:
        prior = found.get(("media", m.fbid))
        if not (prior and prior.storage_path):
            continue  # already counted by the table check
        size = storage.size(prior.storage_path)
        if size is None:
            missing.append(m.fbid)
        elif size != (ready_root / m.uri).stat().st_size:
            # First-stored bytes win, like the frozen key: a warning, never a failure.
            differs.append(m.fbid)
    detail = f"{len(published) - len(absent) - len(missing)} objects in s3://{storage.bucket}"
    if missing:
        detail += f"; missing: {_sample(missing)}"
    if differs:
        detail += f"; size differs: {_sample(differs)}"
    checks.append(Check("every published media object is in the bucket", not missing, detail))

    no_album = [a.fb_album_id for a in albums if ("album", a.fb_album_id) not in found]
    checks.append(Check(
        "every album is in the table",
        not no_album,
        f"{len(albums) - len(no_album)} of {len(albums)} present"
        + (f"; missing: {_sample(no_album)}" if no_album else ""),
    ))

    media_skipped = sum(1 for s in result.skipped_deleted if s.startswith("media:"))
    accounted = (result.media_inserted + result.media_updated + media_skipped
                 + len(result.failed) + len(result.orphans))
    checks.append(Check(
        "every manifest item is accounted for",
        accounted == len(data.media),
        f"inserted={result.media_inserted} updated={result.media_updated} "
        f"skipped_deleted={media_skipped} failed={len(result.failed)} "
        f"orphans={len(result.orphans)} manifest={len(data.media)}",
    ))
    return checks


def publish(
    ready_root: Path,
    workspace_id: str,
    env: Env,
    storage: S3Storage,
    tables: dynamo.Tables,
    identity: tuple[str, str],
) -> PublishResult:
    result = PublishResult(
        env=env.name, kind=env.kind, identity=identity[0], bucket=storage.bucket,
        table_prefix=tables.prefix, workspace_id=workspace_id, ok=False,
        preflight=preflight(env, storage, tables, identity), publish=None, verify=None,
    )
    if not all(c.ok for c in result.preflight):
        return result
    result.publish = load(ready_root, workspace_id, storage, tables)
    result.verify = verify(ready_root, result.publish, storage, tables)
    result.ok = not result.publish.errors and all(c.ok for c in result.verify)
    return result
