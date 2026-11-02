"""Every boto3 DynamoDB call the loader makes lives here.

Client, the per-type table specs, table admin, probe, counts, scan, the `BatchGetItem` pre-fetch
and the one `UpdateItem` builder (Official-Schema §5.2). Each item type has its own table
(`TABLES`), named `<prefix>-<suffix>`. The loader writes album/media items with `UpdateItem`
**only**: `PutItem`, `BatchWriteItem` and `batch_writer()` replace the whole item and would wipe
every CMS-owned attribute on it. What may be written is decided in `items.py`; this module only
says how.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from .items import SK_META, Update
from .storage import ENDPOINT_CONNECT_TIMEOUT, ENDPOINT_READ_TIMEOUT, probe_endpoint

if TYPE_CHECKING:
    from ..config import Settings

DEFAULT_REGION = "ap-southeast-1"
BATCH_GET_LIMIT = 100  # DynamoDB's cap on keys per BatchGetItem
_WAITER = {"Delay": 1, "MaxAttempts": 30}

_serializer = TypeSerializer()
_deserializer = TypeDeserializer()


# --- the tables ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Index:
    name: str
    hash: str
    range: str | None


@dataclass(frozen=True)
class TableSpec:
    suffix: str
    hash: str
    range: str | None = None
    indexes: tuple[Index, ...] = ()


TABLES: dict[str, TableSpec] = {
    "album": TableSpec("album", "id", indexes=(
        Index("by-category", "category_id", "date"),
        Index("by-department", "department_id", "date"),
        Index("featured", "featured_pk", "date"),
    )),
    "media": TableSpec("media", "id", indexes=(
        Index("by-album", "album_id", "creation_at"),
        Index("by-section", "loose_section", "creation_at"),
        Index("by-category", "category_id", "creation_at"),
        Index("featured", "featured_pk", "creation_at"),
    )),
    "credit": TableSpec("credit", "media_id", "staffer_id", indexes=(
        Index("by-staffer", "staffer_id", "media_id"),
    )),
    # parent_key = album#<id> / media#<id>: a derived album shares its first photo's fbid.
    "featuring": TableSpec("featuring", "parent_key", "staffer_id", indexes=(
        Index("by-staffer", "staffer_id", "parent_key"),
    )),
    "staffer": TableSpec("staffer", "id"),
    "staff_term": TableSpec("staff-term", "staffer_id", "term", indexes=(
        Index("by-term", "term", "staff_group"),
    )),
    "department": TableSpec("department", "id"),
    "category": TableSpec("category", "id", indexes=(
        Index("by-channel", "channel_id", "category_name"),
        Index("by-service", "service_id", "category_name"),
    )),
    "channel": TableSpec("channel", "id"),
    "service": TableSpec("service", "id"),
    "users": TableSpec("users", "id"),
}
KINDS: tuple[str, ...] = tuple(TABLES)
# The tables the loader's role may describe and scan on AWS (spec §3.3); never users (D5).
LOADER_KINDS: tuple[str, ...] = ("album", "media", "credit", "featuring", "staffer")
# Uniqueness guards share their type's table under `id = UNIQUE#<attr>#<normalized>`.
GUARD_PREFIX = "UNIQUE#"
GUARDED = frozenset({"staffer", "service", "users"})


@dataclass(frozen=True)
class Tables:
    """A low-level `dynamodb` client bound to one table prefix."""

    client: Any
    prefix: str
    # Table create/delete/reset are allowed only on an emulator (floci, moto), never on AWS.
    on_emulator: bool

    def name(self, kind: str) -> str:
        return f"{self.prefix}-{TABLES[kind].suffix}"

    def probed(self) -> tuple[str, ...]:
        """The kinds the probe, counts and the ready guard cover."""
        return KINDS if self.on_emulator else LOADER_KINDS


class NotOnEmulator(Exception):
    """Table admin was asked of real AWS. Production tables come from Terraform."""


def connect(prefix: str, endpoint_url: str | None, region: str) -> Tables:
    """An emulator client (dummy creds, one attempt) or a real-AWS one (default credential chain).

    Both bound connect/read timeouts, so an offline machine can't wait out botocore's 60s x 3.
    """
    if endpoint_url:
        client = boto3.client(
            "dynamodb",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id="test",  # real credentials never travel to an emulator
            aws_secret_access_key="test",
            config=BotoConfig(
                connect_timeout=ENDPOINT_CONNECT_TIMEOUT,
                read_timeout=ENDPOINT_READ_TIMEOUT,
                retries={"max_attempts": 1},
            ),
        )
        return Tables(client, prefix, on_emulator=True)
    client = boto3.client(
        "dynamodb",
        region_name=region,
        config=BotoConfig(
            connect_timeout=ENDPOINT_CONNECT_TIMEOUT,
            read_timeout=ENDPOINT_READ_TIMEOUT,
            retries={"mode": "standard", "max_attempts": 2},
        ),
    )
    return Tables(client, prefix, on_emulator=False)


def from_settings(s: Settings) -> Tables:
    if not s.dynamodb_table_prefix:
        raise ValueError("ARCHIVENETWORK_DYNAMODB_TABLE_PREFIX is not set")
    # `.env.example` ships ARCHIVENETWORK_S3_REGION= empty, hence the fallback.
    return connect(s.dynamodb_table_prefix, s.dynamodb_endpoint_url, s.s3_region or DEFAULT_REGION)


# --- probe -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Probe:
    endpoint: str  # the emulator URL, or "AWS (<region>)"
    endpoint_reachable: bool
    prefix: str
    tables: dict[str, str]  # every probed kind -> its table name
    missing: list[str]  # probed kinds with no table, in KINDS order
    table_exists: bool  # reachable, not refused, nothing missing
    # Reachable, but DynamoDB said no (e.g. AccessDenied): not the same as "no such table".
    refused: bool = False
    reason: str | None = None


def _is_aws_host(url: str) -> bool:
    return (urlsplit(url).hostname or "").endswith(".amazonaws.com")


def _endpoint_label(t: Tables) -> str:
    url = t.client.meta.endpoint_url
    return f"AWS ({t.client.meta.region_name})" if _is_aws_host(url) else url


def probe(t: Tables) -> Probe:
    """Is the endpoint up, and which of the probed tables exist? Never raises."""
    label = _endpoint_label(t)
    url = t.client.meta.endpoint_url
    tables = {kind: t.name(kind) for kind in t.probed()}

    def down(reason: str | None) -> Probe:
        return Probe(label, False, t.prefix, tables, [], False, reason=reason)

    # A bounded TCP check first, so a stopped container answers in ~1s. moto keeps the AWS URL
    # and only patches botocore, so a raw socket to it would test the real network instead.
    if t.on_emulator and not _is_aws_host(url):
        tcp = probe_endpoint(url)
        if not tcp.reachable:
            return down(tcp.reason)
    missing: list[str] = []
    for kind, name in tables.items():
        try:
            t.client.describe_table(TableName=name)
        except ClientError as exc:
            err = exc.response.get("Error", {})
            code = err.get("Code", "")
            if code == "ResourceNotFoundException":
                missing.append(kind)
                continue
            return Probe(label, True, t.prefix, tables, [], False, refused=True,
                         reason=f"{code}: {err.get('Message', '')}".strip())
        except BotoCoreError as exc:
            return down(str(exc))
    return Probe(label, True, t.prefix, tables, missing, not missing)


# --- table admin (emulator only) -------------------------------------------------------------


def _require_emulator(t: Tables) -> None:
    if not t.on_emulator:
        raise NotOnEmulator(
            f"refusing to create or delete the {t.prefix!r} tables on real AWS; production "
            "tables come from Terraform"
        )


def _key_schema(hash_: str, range_: str | None) -> list[dict]:
    return [{"AttributeName": hash_, "KeyType": "HASH"}] + (
        [{"AttributeName": range_, "KeyType": "RANGE"}] if range_ else []
    )


def _create_args(name: str, spec: TableSpec) -> dict:
    attrs = [spec.hash, spec.range] + [a for ix in spec.indexes for a in (ix.hash, ix.range)]
    args: dict = {
        "TableName": name,
        "BillingMode": "PAY_PER_REQUEST",
        "AttributeDefinitions": [
            {"AttributeName": a, "AttributeType": "S"} for a in dict.fromkeys(attrs) if a
        ],
        "KeySchema": _key_schema(spec.hash, spec.range),
    }
    if spec.indexes:
        args["GlobalSecondaryIndexes"] = [
            {
                "IndexName": ix.name,
                "KeySchema": _key_schema(ix.hash, ix.range),
                "Projection": {"ProjectionType": "ALL"},
            }
            for ix in spec.indexes
        ]
    return args


def create_tables(t: Tables) -> list[str]:
    """Create every missing table from `TABLES`. Returns the kinds created (`[]` = all existed)."""
    _require_emulator(t)
    created: list[str] = []
    for kind, spec in TABLES.items():
        try:
            t.client.create_table(**_create_args(t.name(kind), spec))
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ResourceInUseException":
                continue
            raise
        created.append(kind)
    # Wait after issuing every create, so the tables come up in parallel.
    for kind in created:
        t.client.get_waiter("table_exists").wait(TableName=t.name(kind), WaiterConfig=_WAITER)
    return created


def delete_tables(t: Tables) -> list[str]:
    """Drop every table. Returns the kinds deleted (`[]` = there were none)."""
    _require_emulator(t)
    deleted: list[str] = []
    for kind in KINDS:
        try:
            t.client.delete_table(TableName=t.name(kind))
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ResourceNotFoundException":
                continue
            raise
        deleted.append(kind)
    for kind in deleted:
        t.client.get_waiter("table_not_exists").wait(TableName=t.name(kind), WaiterConfig=_WAITER)
    return deleted


# --- reads -----------------------------------------------------------------------------------


def _plain(v: Any) -> Any:
    """Decimal -> int when integral (else float), recursively through maps and lists."""
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_plain(x) for x in v]
    return v


def _scan(t: Tables, **kw) -> list[dict]:
    items: list[dict] = []
    for page in t.client.get_paginator("scan").paginate(TableName=t.name, **kw):
        items.extend(page.get("Items", []))
    return items


_PREFIX = {"album": "ALBUM#", "media": "MEDIA#"}


def counts(t: Tables) -> dict[str, int]:
    """`#META` items per type; edges (`CREDIT#`, `FEAT#`) and other types never count."""
    out = {"album": 0, "media": 0}
    raw = _scan(t, ProjectionExpression="#pk, #sk",
                ExpressionAttributeNames={"#pk": "PK", "#sk": "SK"})
    for it in raw:
        if it["SK"]["S"] != SK_META:
            continue
        for kind, prefix in _PREFIX.items():
            if it["PK"]["S"].startswith(prefix):
                out[kind] += 1
    return out


def scan_items(t: Tables, kind: Literal["album", "media"] | None = None) -> list[dict]:
    """The whole table as plain Python, optionally only one type's `#META` items, sorted by PK."""
    items = [
        _plain({k: _deserializer.deserialize(v) for k, v in it.items()}) for it in _scan(t)
    ]
    if kind is not None:
        prefix = _PREFIX[kind]
        items = [i for i in items if i["PK"].startswith(prefix) and i["SK"] == SK_META]
    return sorted(items, key=lambda i: (i["PK"], i["SK"]))


@dataclass(frozen=True)
class Existing:
    storage_path: str | None
    deleted: bool


def prefetch(t: Tables, pks: list[str]) -> dict[str, Existing]:
    """The items that already exist: their frozen key and whether the CMS tombstoned them.

    BatchGetItem takes at most 100 distinct keys and may hand some back as UnprocessedKeys;
    missing either would make every item past the first batch read as an insert.
    """
    unique = list(dict.fromkeys(pks))
    found: dict[str, Existing] = {}
    for i in range(0, len(unique), BATCH_GET_LIMIT):
        chunk = unique[i:i + BATCH_GET_LIMIT]
        req: dict = {
            t.name: {
                "Keys": [{"PK": {"S": pk}, "SK": {"S": SK_META}} for pk in chunk],
                "ProjectionExpression": "#pk, #sp, #del",
                "ExpressionAttributeNames": {
                    "#pk": "PK", "#sp": "storage_path", "#del": "deleted_at",
                },
                "ConsistentRead": True,
            }
        }
        attempt = 0
        while req:
            if attempt:
                time.sleep(min(0.05 * 2**attempt, 1.0))
            resp = t.client.batch_get_item(RequestItems=req)
            for it in resp.get("Responses", {}).get(t.name, []):
                found[it["PK"]["S"]] = Existing(
                    storage_path=it.get("storage_path", {}).get("S"),
                    deleted="deleted_at" in it,
                )
            req = resp.get("UnprocessedKeys") or {}
            attempt += 1
    return found


# --- the one write ---------------------------------------------------------------------------


def upsert(t: Tables, u: Update) -> Literal["written", "skipped_deleted"]:
    """The §5.2 `UpdateItem`: SET L values, if_not_exists L1 values, REMOVE absent L values.

    The condition keeps a CMS tombstone authoritative even if it landed after the pre-fetch.
    """
    names: dict[str, str] = {"#del": "deleted_at"}
    values: dict[str, Any] = {}
    sets: list[str] = []
    removes: list[str] = []
    for i, (attr, value) in enumerate(u.refresh.items()):
        names[f"#r{i}"] = attr
        if value is None:
            removes.append(f"#r{i}")
        else:
            values[f":r{i}"] = _serializer.serialize(value)
            sets.append(f"#r{i} = :r{i}")
    for i, (attr, value) in enumerate(u.set_once.items()):
        names[f"#o{i}"] = attr
        values[f":o{i}"] = _serializer.serialize(value)
        sets.append(f"#o{i} = if_not_exists(#o{i}, :o{i})")
    expr = "SET " + ", ".join(sets)
    if removes:
        expr += " REMOVE " + ", ".join(removes)
    try:
        t.client.update_item(
            TableName=t.name,
            Key={"PK": {"S": u.pk}, "SK": {"S": SK_META}},
            UpdateExpression=expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression="attribute_not_exists(#del)",
            ReturnValues="NONE",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return "skipped_deleted"
        raise
    return "written"
