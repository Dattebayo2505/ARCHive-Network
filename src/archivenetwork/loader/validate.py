"""Assertions about what actually landed in the table and the object store (Official-Schema §5.4).

DynamoDB enforces no referential integrity, so these checks are the only guard. One full Scan
feeds all of them. The table accumulates across workspaces and CMS edits, so reconciliation with
the manifests is **one-way**: every manifest item must be in the table, not the reverse.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import dynamo
from .items import SK_META
from .read import read_ready
from .storage import Storage


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


def _key_id(pk: str) -> str:
    return pk.split("#", 1)[1]


def validate(ready_root: Path, storage: Storage, table: dynamo.Table) -> list[Check]:
    data = read_ready(ready_root)
    items = dynamo.scan_items(table)
    meta = [i for i in items if i["SK"] == SK_META]
    media = [i for i in meta if i["PK"].startswith("MEDIA#")]
    album_ids = {_key_id(i["PK"]) for i in meta if i["PK"].startswith("ALBUM#")}
    staffer_ids = {_key_id(i["PK"]) for i in meta if i["PK"].startswith("STAFFER#")}
    checks: list[Check] = []

    # 1. A tombstoned item is excluded: the CMS may have removed its object along with it.
    missing = [
        _key_id(m["PK"])
        for m in media
        if "deleted_at" not in m
        and not (m.get("storage_path") and storage.exists(m["storage_path"]))
    ]
    checks.append(
        Check(
            "every media.storage_path resolves in the store",
            not missing,
            f"{len(missing)} missing, e.g. {missing[:3]}",
        )
    )

    dangling = [
        _key_id(m["PK"]) for m in media if m.get("album_id") and m["album_id"] not in album_ids
    ]
    checks.append(
        Check(
            "every media.album_id names an existing album",
            not dangling,
            f"{len(dangling)} dangling, e.g. {dangling[:3]}",
        )
    )

    edges = [i for i in items if i["SK"].startswith(("CREDIT#", "FEAT#"))]
    orphan_edges = [
        f"{e['PK']}/{e['SK']}" for e in edges if _key_id(e["SK"]) not in staffer_ids
    ]
    checks.append(
        Check(
            "every credit and featuring edge names an existing staffer",
            not orphan_edges,
            f"{len(orphan_edges)} of {len(edges)} edges dangling, e.g. {orphan_edges[:3]}",
        )
    )

    no_ts = [_key_id(m["PK"]) for m in media if not m.get("creation_at")]
    checks.append(
        Check(
            "every media has a creation_at",
            not no_ts,
            f"{len(no_ts)} without, e.g. {no_ts[:3]}",
        )
    )

    # 5. Media has no `source`: an fbid marks an FB item, its absence a CMS-made one.
    # A missing storage_path is check 1's failure, so only a present one is prefix-checked here.
    miskeyed = []
    for m in media:
        own_id, path = _key_id(m["PK"]), m.get("storage_path")
        if m.get("fbid"):
            bad = m["fbid"] != own_id or m.get("id") != own_id
            bad = bad or bool(path and not path.startswith("fb-exports/"))
        else:
            bad = bool(path and not path.startswith("cms/"))
        if bad:
            miskeyed.append(own_id)
    checks.append(
        Check(
            "every media with an fbid is keyed by it",
            not miskeyed,
            f"{len(miskeyed)} miskeyed, e.g. {miskeyed[:3]}",
        )
    )

    expected = {m.fbid for m in data.media if (ready_root / m.uri).exists()}
    in_table = {m["fbid"] for m in media if m.get("fbid")}
    absent = sorted(expected - in_table)
    others = sum(1 for m in media if m.get("fbid") not in expected)
    checks.append(
        Check(
            "every manifest item is in the table",
            not absent,
            f"manifests={len(expected)} missing={absent[:3]} others_in_table={others}",
        )
    )

    # The ready folder holds no file the manifests forgot to mention. A manifest-driven ETL
    # cannot see such a file, so it would be silently dropped — the `n01` class of bug.
    media_dir = ready_root / "posts" / "media"
    on_disk = {
        p.relative_to(ready_root).as_posix()
        for p in media_dir.rglob("*")
        if p.is_file()
    }
    unreferenced = sorted(on_disk - {m.uri for m in data.media})
    checks.append(
        Check(
            "every file in ready/ is referenced by a manifest",
            not unreferenced,
            f"{len(unreferenced)} unreferenced, e.g. {unreferenced[:3]}",
        )
    )

    return checks
