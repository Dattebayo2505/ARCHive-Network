"""Every boto3 DynamoDB call the loader makes lives here.

Client, table admin, probe, counts, scan, the `BatchGetItem` pre-fetch and the one `UpdateItem`
builder (Official-Schema §5.2). The loader writes album/media items with `UpdateItem` **only**:
`PutItem`, `BatchWriteItem` and `batch_writer()` replace the whole item and would wipe every
CMS-owned attribute on it. What may be written is decided in `items.py`; this module only says how.
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
_KEY_ATTRS = ["PK", "SK", "GSI1PK", "GSI1SK", "GSI2PK", "GSI3PK", "GSI3SK"]
_GSIS = [("GSI1", "GSI1PK", "GSI1SK"), ("GSI2", "GSI2PK", None), ("GSI3", "GSI3PK", "GSI3SK")]

_serializer = TypeSerializer()
_deserializer = TypeDeserializer()


@dataclass(frozen=True)
class Table:
    """A low-level `dynamodb` client bound to one table name."""

    client: Any
    name: str
    # Table create/delete/reset are allowed only on an emulator (floci, moto), never on AWS.
    on_emulator: bool


class NotOnEmulator(Exception):
    """Table admin was asked of real AWS. Production tables come from Terraform."""


def connect(table_name: str, endpoint_url: str | None, region: str) -> Table:
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
        return Table(client, table_name, on_emulator=True)
    client = boto3.client(
        "dynamodb",
        region_name=region,
        config=BotoConfig(
            connect_timeout=ENDPOINT_CONNECT_TIMEOUT,
            read_timeout=ENDPOINT_READ_TIMEOUT,
            retries={"mode": "standard", "max_attempts": 2},
        ),
    )
    return Table(client, table_name, on_emulator=False)


def from_settings(s: Settings) -> Table:
    if not s.dynamodb_table:
        raise ValueError("ARCHIVENETWORK_DYNAMODB_TABLE is not set")
    # `.env.example` ships ARCHIVENETWORK_S3_REGION= empty, hence the fallback.
    return connect(s.dynamodb_table, s.dynamodb_endpoint_url, s.s3_region or DEFAULT_REGION)


# --- probe -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Probe:
    endpoint: str  # the emulator URL, or "AWS (<region>)"
    endpoint_reachable: bool
    table: str
    table_exists: bool
    # Reachable, but DynamoDB said no (e.g. AccessDenied): not the same as "no such table".
    refused: bool = False
    reason: str | None = None


def _is_aws_host(url: str) -> bool:
    return (urlsplit(url).hostname or "").endswith(".amazonaws.com")


def _endpoint_label(t: Table) -> str:
    url = t.client.meta.endpoint_url
    return f"AWS ({t.client.meta.region_name})" if _is_aws_host(url) else url


def probe(t: Table) -> Probe:
    """Is the endpoint up, and does the table exist? Never raises."""
    label = _endpoint_label(t)
    url = t.client.meta.endpoint_url
    # A bounded TCP check first, so a stopped container answers in ~1s. moto keeps the AWS URL
    # and only patches botocore, so a raw socket to it would test the real network instead.
    if t.on_emulator and not _is_aws_host(url):
        tcp = probe_endpoint(url)
        if not tcp.reachable:
            return Probe(label, False, t.name, False, reason=tcp.reason)
    try:
        t.client.describe_table(TableName=t.name)
    except ClientError as exc:
        err = exc.response.get("Error", {})
        code = err.get("Code", "")
        if code == "ResourceNotFoundException":
            return Probe(label, True, t.name, False)
        return Probe(label, True, t.name, False, refused=True,
                     reason=f"{code}: {err.get('Message', '')}".strip())
    except BotoCoreError as exc:
        return Probe(label, False, t.name, False, reason=str(exc))
    return Probe(label, True, t.name, True)


# --- table admin (emulator only) -------------------------------------------------------------


def _require_emulator(t: Table) -> None:
    if not t.on_emulator:
        raise NotOnEmulator(
            f"refusing to create or delete {t.name!r} on real AWS; production tables come "
            "from Terraform"
        )


def create_table(t: Table) -> bool:
    """Create the single table with its three GSIs. True = created, False = it existed."""
    _require_emulator(t)
    try:
        t.client.create_table(
            TableName=t.name,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": a, "AttributeType": "S"} for a in _KEY_ATTRS],
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": name,
                    "KeySchema": [{"AttributeName": pk, "KeyType": "HASH"}]
                    + ([{"AttributeName": sk, "KeyType": "RANGE"}] if sk else []),
                    "Projection": {"ProjectionType": "ALL"},
                }
                for name, pk, sk in _GSIS
            ],
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceInUseException":
            return False
        raise
    t.client.get_waiter("table_exists").wait(TableName=t.name, WaiterConfig=_WAITER)
    return True


def delete_table(t: Table) -> bool:
    """Drop the table. True = deleted, False = there was none."""
    _require_emulator(t)
    try:
        t.client.delete_table(TableName=t.name)
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceNotFoundException":
            return False
        raise
    t.client.get_waiter("table_not_exists").wait(TableName=t.name, WaiterConfig=_WAITER)
    return True


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


def _scan(t: Table, **kw) -> list[dict]:
    items: list[dict] = []
    for page in t.client.get_paginator("scan").paginate(TableName=t.name, **kw):
        items.extend(page.get("Items", []))
    return items


_PREFIX = {"album": "ALBUM#", "media": "MEDIA#"}


def counts(t: Table) -> dict[str, int]:
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


def scan_items(t: Table, kind: Literal["album", "media"] | None = None) -> list[dict]:
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


def prefetch(t: Table, pks: list[str]) -> dict[str, Existing]:
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


def upsert(t: Table, u: Update) -> Literal["written", "skipped_deleted"]:
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
