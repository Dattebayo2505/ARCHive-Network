"""dynamo.py on moto: table admin, probe, counts, scan, the pre-fetch and the §5.2 UpdateItem.

The write-rule tests are the spike's `write_rule_checks` + `override_checks`
(docs/spikes/2026-10-30-dynamodb-local-spike.py), ported onto `dynamo.upsert`.
"""

import pytest
from botocore.exceptions import ClientError

from archivenetwork.loader import dynamo
from archivenetwork.loader.items import Update

T1 = "2026-11-02T03:04:05Z"
T2 = "2026-11-09T03:04:05Z"


def _get(ddb, kind: str, item_id: str) -> dict:
    return ddb.client.get_item(
        TableName=ddb.name(kind), Key={"id": {"S": item_id}}, ConsistentRead=True
    ).get("Item", {})


def _media(fbid="900001", description="first", path="fb-exports/a/first/900001.jpg",
           created=T1, loaded=T1, **extra) -> Update:
    refresh = {"title": "FB title", "description": description, "loaded_at": loaded,
               "album_id": "111", "creation_at": "2026-07-01T00:00:00Z"}
    refresh.update(extra)
    return Update("media", fbid, refresh, {"storage_path": path, "fbid": fbid,
                                           "created_at": created})


def _album(album_id="111") -> Update:
    return Update("album", album_id, {"title": "A", "loaded_at": T1},
                  {"kind": "photo", "source": "fb_export", "created_at": T1})


def _cms(ddb, kind: str, item_id: str, expr: str, values: dict,
         names: dict | None = None) -> None:
    kw = {"ExpressionAttributeNames": names} if names else {}
    ddb.client.update_item(TableName=ddb.name(kind), Key={"id": {"S": item_id}},
                           UpdateExpression=expr, ExpressionAttributeValues=values, **kw)


# --- connect / table admin / probe -----------------------------------------------------------


def test_connect_to_an_emulator_uses_dummy_credentials_and_bounded_timeouts():
    t = dynamo.connect("t", "http://127.0.0.1:4566", "ap-southeast-1")
    assert t.on_emulator is True and t.prefix == "t"
    assert t.client.meta.endpoint_url == "http://127.0.0.1:4566"
    assert t.client._request_signer._credentials.access_key == "test"
    cfg = t.client.meta.config
    assert cfg.connect_timeout == 3 and cfg.read_timeout == 10
    assert cfg.retries["total_max_attempts"] == 2  # botocore normalises max_attempts=1


def test_connect_without_an_endpoint_is_real_aws(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "x")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "y")
    t = dynamo.connect("t", None, "ap-southeast-1")
    assert t.on_emulator is False
    assert t.client.meta.endpoint_url.startswith("https://dynamodb.ap-southeast-1.")
    assert t.client.meta.config.retries["mode"] == "standard"


def test_from_settings_falls_back_to_the_default_region():
    from archivenetwork.config import Settings

    s = Settings(_env_file=None, dynamodb_table_prefix="tbl", s3_region="")
    t = dynamo.from_settings(s)
    assert t.prefix == "tbl" and t.client.meta.region_name == "ap-southeast-1"


def test_from_settings_requires_the_prefix():
    from archivenetwork.config import Settings

    s = Settings(_env_file=None, dynamodb_table_prefix=None, dynamodb_table="legacy")
    with pytest.raises(ValueError, match="ARCHIVENETWORK_DYNAMODB_TABLE_PREFIX"):
        dynamo.from_settings(s)


def test_table_names_follow_the_prefix():
    t = dynamo.connect("p", "http://127.0.0.1:4566", "ap-southeast-1")
    assert t.name("staff_term") == "p-staff-term"
    assert t.name("users") == "p-users"
    assert t.name("album") == "p-album"


def test_tables_cover_every_kind_in_order():
    assert tuple(dynamo.TABLES) == dynamo.KINDS
    assert len(dynamo.KINDS) == 11


def _key_schema(hash_: str, range_: str | None) -> list[dict]:
    return [{"AttributeName": hash_, "KeyType": "HASH"}] + (
        [{"AttributeName": range_, "KeyType": "RANGE"}] if range_ else []
    )


def test_created_tables_match_the_spec(ddb):
    for kind, spec in dynamo.TABLES.items():
        desc = ddb.client.describe_table(TableName=ddb.name(kind))["Table"]
        assert desc["KeySchema"] == _key_schema(spec.hash, spec.range), kind
        assert desc["BillingModeSummary"]["BillingMode"] == "PAY_PER_REQUEST"
        gsis = {g["IndexName"]: g["KeySchema"] for g in desc.get("GlobalSecondaryIndexes", [])}
        assert gsis == {ix.name: _key_schema(ix.hash, ix.range) for ix in spec.indexes}, kind
        if not spec.indexes:
            assert not desc.get("GlobalSecondaryIndexes"), kind  # moto returns [], AWS omits it


def test_no_table_has_pk_sk_or_gsi_attributes(ddb):
    for kind in dynamo.KINDS:
        desc = ddb.client.describe_table(TableName=ddb.name(kind))["Table"]
        names = [a["AttributeName"] for a in desc["AttributeDefinitions"]]
        assert not [n for n in names if n in ("PK", "SK") or n.startswith("GSI")], kind


def test_create_tables_is_idempotent(ddb):
    assert dynamo.create_tables(ddb) == []


def test_delete_then_create_tables(ddb):
    assert dynamo.delete_tables(ddb) == list(dynamo.KINDS)
    assert dynamo.probe(ddb).missing == list(dynamo.KINDS)
    assert dynamo.create_tables(ddb) == list(dynamo.KINDS)
    assert dynamo.probe(ddb).table_exists is True


def test_table_admin_refuses_real_aws(ddb):
    aws = dynamo.Tables(ddb.client, ddb.prefix, on_emulator=False)
    with pytest.raises(dynamo.NotOnEmulator):
        dynamo.delete_tables(aws)
    with pytest.raises(dynamo.NotOnEmulator):
        dynamo.create_tables(aws)
    assert dynamo.probe(ddb).table_exists is True  # nothing was dropped


def test_probe_reports_all_tables(ddb):
    p = dynamo.probe(ddb)
    assert p.endpoint_reachable and p.table_exists and not p.refused
    assert p.missing == [] and p.prefix == ddb.prefix
    assert p.tables["album"] == ddb.name("album")
    assert set(p.tables) == set(dynamo.KINDS)


def test_probe_names_the_missing_tables(ddb):
    ddb.client.delete_table(TableName=ddb.name("credit"))
    p = dynamo.probe(ddb)
    assert p.missing == ["credit"]
    assert p.table_exists is False and p.endpoint_reachable is True and p.refused is False


def test_probe_on_aws_covers_only_the_loader_tables(ddb):
    aws = dynamo.Tables(ddb.client, ddb.prefix, on_emulator=False)
    ddb.client.delete_table(TableName=ddb.name("users"))
    ddb.client.delete_table(TableName=ddb.name("channel"))
    p = dynamo.probe(aws)
    assert set(p.tables) == set(dynamo.LOADER_KINDS)
    assert p.table_exists is True and p.missing == []


def test_probe_keeps_a_refusal_distinct_from_a_missing_table(ddb, monkeypatch):
    real = ddb.client.describe_table

    def denied(**kw):
        if kw["TableName"] == ddb.name("staffer"):
            raise ClientError(
                {"Error": {"Code": "AccessDeniedException", "Message": "not authorized"}},
                "DescribeTable",
            )
        return real(**kw)

    monkeypatch.setattr(ddb.client, "describe_table", denied)
    p = dynamo.probe(ddb)
    assert p.endpoint_reachable is True and p.table_exists is False
    assert p.refused is True and "AccessDenied" in p.reason and p.missing == []


def test_probe_reports_an_unreachable_endpoint_without_raising():
    p = dynamo.probe(dynamo.connect("t", "http://127.0.0.1:1", "ap-southeast-1"))
    assert p.endpoint_reachable is False and p.reason
    assert p.endpoint == "http://127.0.0.1:1"
    assert p.missing == [] and p.tables["album"] == "t-album"


def test_featuring_on_an_album_and_a_media_with_the_same_id_are_two_edges(ddb):
    # A derived album's id is its first photo's fbid, so the typed parent_key keeps them apart.
    for parent in ("album", "media"):
        ddb.client.put_item(TableName=ddb.name("featuring"), Item={
            "parent_key": {"S": f"{parent}#g01"}, "staffer_id": {"S": "s1"},
            "parent_type": {"S": parent}, "parent_id": {"S": "g01"},
        })
    assert ddb.client.scan(TableName=ddb.name("featuring"))["Count"] == 2


# --- upsert: the write rules -----------------------------------------------------------------


def test_upsert_insert_then_refresh_keeps_set_once(ddb):
    assert dynamo.upsert(ddb, _media()) == "written"
    v2 = _media(description="second", path="fb-exports/a/RENAMED/900001.jpg",
                created="2099-01-01T00:00:00Z", loaded=T2)
    assert dynamo.upsert(ddb, v2) == "written"
    it = _get(ddb, "media", "900001")
    assert it["description"]["S"] == "second"
    assert it["storage_path"]["S"] == "fb-exports/a/first/900001.jpg"  # frozen
    assert it["created_at"]["S"] == T1
    assert it["loaded_at"]["S"] == T2
    assert it["id"]["S"] == it["fbid"]["S"] == "900001"  # the Key wrote `id` on insert


def test_upsert_targets_the_kinds_own_table(ddb):
    dynamo.upsert(ddb, _album("g01"))
    assert _get(ddb, "album", "g01")["title"]["S"] == "A"
    assert _get(ddb, "media", "g01") == {}


def test_upsert_removes_an_l_value_the_export_dropped(ddb):
    dynamo.upsert(ddb, _media())
    dynamo.upsert(ddb, _media(description=None))
    assert "description" not in _get(ddb, "media", "900001")


def test_upsert_never_writes_null(ddb):
    dynamo.upsert(ddb, _media(description=None, hashtags=None, album_id=None))
    it = _get(ddb, "media", "900001")
    assert not [k for k, v in it.items() if "NULL" in v]
    assert {"description", "hashtags", "album_id"}.isdisjoint(it)


def test_upsert_serialises_lists_as_l_of_s_and_bools(ddb):
    dynamo.upsert(ddb, _media(hashtags=["ARCHEVT", "ArchersNetwork"]))
    assert _get(ddb, "media", "900001")["hashtags"] == {"L": [{"S": "ARCHEVT"},
                                                              {"S": "ArchersNetwork"}]}


def test_cms_edit_survives_a_reload(ddb):
    """Spec §8 regression: every CMS-owned attribute is intact after the loader rewrites."""
    dynamo.upsert(ddb, _media())
    _cms(ddb, "media", "900001",
         "SET overrides = :o, is_featured = :f, updated_at = :u, updated_by = :b, "
         "category_id = :c, featured_pk = :fp",
         {":o": {"M": {"description": {"S": "CMS text"}}}, ":f": {"BOOL": True},
          ":u": {"S": T1}, ":b": {"S": "editor-1"}, ":c": {"S": "cat-1"},
          ":fp": {"S": "FEATURED"}})
    before = _get(ddb, "media", "900001")
    dynamo.upsert(ddb, _media(description="second", loaded=T2))
    after = _get(ddb, "media", "900001")
    for k in ("overrides", "is_featured", "updated_at", "updated_by", "category_id",
              "featured_pk"):
        assert after[k] == before[k], k
    assert after["description"]["S"] == "second"


def test_tombstone_wins_and_leaves_the_item_untouched(ddb):
    dynamo.upsert(ddb, _media())
    _cms(ddb, "media", "900001", "SET deleted_at = :d", {":d": {"S": T1}})
    before = _get(ddb, "media", "900001")
    assert dynamo.upsert(ddb, _media(description="resurrect", loaded=T2)) == "skipped_deleted"
    assert _get(ddb, "media", "900001") == before


def test_upsert_reraises_other_client_errors(ddb, monkeypatch):
    def boom(**_kw):
        raise ClientError({"Error": {"Code": "ProvisionedThroughputExceededException",
                                     "Message": "slow down"}}, "UpdateItem")

    monkeypatch.setattr(ddb.client, "update_item", boom)
    with pytest.raises(ClientError):
        dynamo.upsert(ddb, _media())


def test_overrides_survive_and_title_refreshes(ddb):
    """The spike's override_checks: title is L; CMS edits live in `overrides`."""
    fbid = "900010"
    dynamo.upsert(ddb, _media(fbid, description="FB cap v1", title="FB title v1"))
    _cms(ddb, "media", fbid, "SET overrides = if_not_exists(overrides, :e)", {":e": {"M": {}}})
    _cms(ddb, "media", fbid, "SET overrides.title = :t, overrides.description = :c",
         {":t": {"S": "CMS title"}, ":c": {"S": "CMS cap"}})
    dynamo.upsert(ddb, _media(fbid, description=None, title="FB title v2", loaded=T2))
    it = _get(ddb, "media", fbid)
    ov = it["overrides"]["M"]
    assert it["title"]["S"] == "FB title v2"
    assert "description" not in it and ov["description"]["S"] == "CMS cap"
    assert ov["title"]["S"] == "CMS title"

    ddb.client.update_item(TableName=ddb.name("media"), Key={"id": {"S": fbid}},
                           UpdateExpression="REMOVE overrides.title")
    dynamo.upsert(ddb, _media(fbid, description=None, title="FB title v3", loaded=T2))
    it = _get(ddb, "media", fbid)
    assert "title" not in it["overrides"]["M"] and it["title"]["S"] == "FB title v3"


def test_cms_cannot_set_into_a_missing_overrides_map(ddb):
    """Pins the CMS gotcha (Official-Schema §5.1): create the map first."""
    dynamo.upsert(ddb, _media())
    with pytest.raises(ClientError) as exc:
        _cms(ddb, "media", "900001", "SET overrides.title = :t", {":t": {"S": "CMS title"}})
    assert exc.value.response["Error"]["Code"] == "ValidationException"


# --- counts / scan_items ---------------------------------------------------------------------


def test_counts_cover_every_kind(ddb):
    got = dynamo.counts(ddb)
    assert set(got) == set(dynamo.KINDS) and set(got.values()) == {0}


def test_counts_count_each_table(ddb):
    dynamo.upsert(ddb, _media())
    dynamo.upsert(ddb, _album())
    ddb.client.put_item(TableName=ddb.name("credit"),
                        Item={"media_id": {"S": "900001"}, "staffer_id": {"S": "s1"}})
    got = dynamo.counts(ddb)
    assert got["album"] == 1 and got["media"] == 1 and got["credit"] == 1
    assert got["staffer"] == 0


def test_counts_cover_only_the_loader_tables_on_aws(ddb):
    aws = dynamo.Tables(ddb.client, ddb.prefix, on_emulator=False)
    assert set(dynamo.counts(aws)) == set(dynamo.LOADER_KINDS)


def test_counts_and_scans_skip_guard_items(ddb):
    staffer = ddb.name("staffer")
    ddb.client.put_item(TableName=staffer, Item={"id": {"S": "UNIQUE#full_name#carla reyes"},
                                                 "staffer_id": {"S": "s1"}})
    ddb.client.put_item(TableName=staffer, Item={"id": {"S": "s1"},
                                                 "full_name": {"S": "Carla Reyes"}})
    assert dynamo.counts(ddb)["staffer"] == 1
    assert [i["id"] for i in dynamo.scan_items(ddb, "staffer")] == ["s1"]


def test_scan_items_returns_plain_python(ddb):
    dynamo.upsert(ddb, _media(hashtags=["ARCHEVT"]))
    _cms(ddb, "media", "900001", "SET overrides = :o, is_featured = :f, n = :n",
         {":o": {"M": {"rank": {"N": "3"}, "xs": {"L": [{"N": "1"}, {"N": "1.5"}]}}},
          ":f": {"BOOL": True}, ":n": {"N": "7"}})
    (it,) = dynamo.scan_items(ddb, "media")
    assert it["n"] == 7 and type(it["n"]) is int
    assert it["overrides"]["rank"] == 3 and type(it["overrides"]["rank"]) is int
    assert it["overrides"]["xs"] == [1, 1.5] and type(it["overrides"]["xs"][0]) is int
    assert it["hashtags"] == ["ARCHEVT"] and it["is_featured"] is True


def test_scan_items_reads_one_table_sorted_by_its_key(ddb):
    for fbid in ("c", "a", "b"):
        dynamo.upsert(ddb, _media(fbid))
    dynamo.upsert(ddb, _album("1"))
    assert [i["id"] for i in dynamo.scan_items(ddb, "media")] == ["a", "b", "c"]
    assert [i["id"] for i in dynamo.scan_items(ddb, "album")] == ["1"]


def test_scan_items_sorts_an_edge_table_by_hash_then_range(ddb):
    for media_id, staffer_id in (("m2", "s1"), ("m1", "s2"), ("m1", "s1")):
        ddb.client.put_item(TableName=ddb.name("credit"), Item={
            "media_id": {"S": media_id}, "staffer_id": {"S": staffer_id}})
    got = [(i["media_id"], i["staffer_id"]) for i in dynamo.scan_items(ddb, "credit")]
    assert got == [("m1", "s1"), ("m1", "s2"), ("m2", "s1")]


# --- prefetch --------------------------------------------------------------------------------


def test_prefetch_returns_only_existing_with_their_frozen_key_and_tombstone(ddb):
    dynamo.upsert(ddb, _media("a", path="fb-exports/x/a.jpg"))
    dynamo.upsert(ddb, _media("b", path="fb-exports/x/b.jpg"))
    _cms(ddb, "media", "b", "SET deleted_at = :d", {":d": {"S": T1}})
    got = dynamo.prefetch(ddb, [("media", "a"), ("media", "b"), ("media", "nope")])
    assert got == {
        ("media", "a"): dynamo.Existing(storage_path="fb-exports/x/a.jpg", deleted=False),
        ("media", "b"): dynamo.Existing(storage_path="fb-exports/x/b.jpg", deleted=True),
    }


def test_prefetch_keeps_an_album_and_a_media_with_the_same_id_apart(ddb):
    dynamo.upsert(ddb, _album("g01"))
    got = dynamo.prefetch(ddb, [("album", "g01"), ("media", "g01")])
    assert set(got) == {("album", "g01")}


def test_prefetch_of_nothing_is_empty(ddb):
    assert dynamo.prefetch(ddb, []) == {}


def test_prefetch_chunks_past_100_keys(ddb):
    keys = [("media", f"{n:04d}") for n in range(90)] + [("album", f"{n:04d}") for n in range(60)]
    for kind, item_id in keys:
        dynamo.upsert(ddb, _media(item_id) if kind == "media" else _album(item_id))
    got = dynamo.prefetch(ddb, keys + [("media", f"unknown{n}") for n in range(5)])
    assert set(got) == set(keys)


def test_prefetch_dedupes_keys(ddb):
    dynamo.upsert(ddb, _media("a"))
    assert set(dynamo.prefetch(ddb, [("media", "a"), ("media", "a")])) == {("media", "a")}


class _FlakyBatchGet:
    """First reply leaves one key unprocessed; the retry returns it."""

    def __init__(self):
        self.calls = []

    def batch_get_item(self, RequestItems):
        self.calls.append(RequestItems)
        (name, req), = RequestItems.items()
        keys = req["Keys"]
        if len(self.calls) == 1:
            first, rest = keys[:1], keys[1:]
            return {"Responses": {name: [{"id": first[0]["id"]}]},
                    "UnprocessedKeys": {name: dict(req, Keys=rest)}}
        return {"Responses": {name: [{"id": k["id"], "storage_path": {"S": "k"}}
                                     for k in keys]},
                "UnprocessedKeys": {}}


def test_prefetch_follows_unprocessed_keys(monkeypatch):
    monkeypatch.setattr(dynamo.time, "sleep", lambda _s: None)
    fake = _FlakyBatchGet()
    got = dynamo.prefetch(dynamo.Tables(fake, "t", on_emulator=True),
                          [("media", "a"), ("media", "b")])
    assert set(got) == {("media", "a"), ("media", "b")} and len(fake.calls) == 2
    assert got[("media", "b")].storage_path == "k" and got[("media", "a")].storage_path is None
