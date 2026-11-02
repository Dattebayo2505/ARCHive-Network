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


def _get(ddb, pk: str) -> dict:
    return ddb.client.get_item(
        TableName=ddb.name, Key={"PK": {"S": pk}, "SK": {"S": "#META"}}, ConsistentRead=True
    ).get("Item", {})


def _media(pk="MEDIA#900001", description="first", path="fb-exports/a/first/900001.jpg",
           created=T1, loaded=T1, **extra) -> Update:
    refresh = {"title": "FB title", "description": description, "loaded_at": loaded,
               "GSI1PK": "ALBUM#111", "GSI1SK": "2026-07-01T00:00:00Z"}
    refresh.update(extra)
    fbid = pk.split("#", 1)[1]
    return Update(pk, refresh, {"id": fbid, "storage_path": path, "fbid": fbid,
                                "created_at": created})


def _cms(ddb, pk: str, expr: str, values: dict, names: dict | None = None) -> None:
    kw = {"ExpressionAttributeNames": names} if names else {}
    ddb.client.update_item(TableName=ddb.name, Key={"PK": {"S": pk}, "SK": {"S": "#META"}},
                           UpdateExpression=expr, ExpressionAttributeValues=values, **kw)


# --- connect / table admin / probe -----------------------------------------------------------


def test_connect_to_an_emulator_uses_dummy_credentials_and_bounded_timeouts():
    t = dynamo.connect("t", "http://127.0.0.1:4566", "ap-southeast-1")
    assert t.on_emulator is True and t.name == "t"
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

    s = Settings(_env_file=None, dynamodb_table="tbl", s3_region="")
    t = dynamo.from_settings(s)
    assert t.name == "tbl" and t.client.meta.region_name == "ap-southeast-1"


def test_create_table_is_idempotent(ddb):
    assert dynamo.create_table(ddb) is False


def test_delete_then_create(ddb):
    assert dynamo.delete_table(ddb) is True and dynamo.probe(ddb).table_exists is False
    assert dynamo.create_table(ddb) is True and dynamo.probe(ddb).table_exists is True
    assert dynamo.delete_table(ddb) is True and dynamo.delete_table(ddb) is False


def test_created_table_has_the_three_gsis(ddb):
    desc = ddb.client.describe_table(TableName=ddb.name)["Table"]
    gsis = {g["IndexName"]: [k["AttributeName"] for k in g["KeySchema"]]
            for g in desc["GlobalSecondaryIndexes"]}
    assert gsis == {"GSI1": ["GSI1PK", "GSI1SK"], "GSI2": ["GSI2PK"], "GSI3": ["GSI3PK", "GSI3SK"]}
    assert desc["BillingModeSummary"]["BillingMode"] == "PAY_PER_REQUEST"


def test_table_admin_refuses_real_aws(ddb):
    aws = dynamo.Table(ddb.client, ddb.name, on_emulator=False)
    with pytest.raises(dynamo.NotOnEmulator):
        dynamo.delete_table(aws)
    with pytest.raises(dynamo.NotOnEmulator):
        dynamo.create_table(aws)
    assert dynamo.probe(ddb).table_exists is True  # nothing was dropped


def test_probe_reports_an_existing_table(ddb):
    p = dynamo.probe(ddb)
    assert p.endpoint_reachable and p.table_exists and not p.refused and p.table == ddb.name


def test_probe_reports_a_missing_table_on_a_reachable_endpoint(ddb):
    dynamo.delete_table(ddb)
    p = dynamo.probe(ddb)
    assert p.endpoint_reachable is True and p.table_exists is False and p.refused is False


def test_probe_keeps_a_refusal_distinct_from_a_missing_table(ddb, monkeypatch):
    def denied(**_kw):
        raise ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "not authorized"}},
            "DescribeTable",
        )

    monkeypatch.setattr(ddb.client, "describe_table", denied)
    p = dynamo.probe(ddb)
    assert p.endpoint_reachable is True and p.table_exists is False
    assert p.refused is True and "AccessDenied" in p.reason


def test_probe_reports_an_unreachable_endpoint_without_raising():
    p = dynamo.probe(dynamo.connect("t", "http://127.0.0.1:1", "ap-southeast-1"))
    assert p.endpoint_reachable is False and p.reason
    assert p.endpoint == "http://127.0.0.1:1"


# --- upsert: the write rules -----------------------------------------------------------------


def test_upsert_insert_then_refresh_keeps_set_once(ddb):
    assert dynamo.upsert(ddb, _media()) == "written"
    v2 = _media(description="second", path="fb-exports/a/RENAMED/900001.jpg",
                created="2099-01-01T00:00:00Z", loaded=T2)
    assert dynamo.upsert(ddb, v2) == "written"
    it = _get(ddb, "MEDIA#900001")
    assert it["description"]["S"] == "second"
    assert it["storage_path"]["S"] == "fb-exports/a/first/900001.jpg"  # frozen
    assert it["created_at"]["S"] == T1
    assert it["loaded_at"]["S"] == T2
    assert it["id"]["S"] == it["fbid"]["S"] == "900001"


def test_upsert_removes_an_l_value_the_export_dropped(ddb):
    dynamo.upsert(ddb, _media())
    dynamo.upsert(ddb, _media(description=None))
    assert "description" not in _get(ddb, "MEDIA#900001")


def test_upsert_never_writes_null(ddb):
    dynamo.upsert(ddb, _media(description=None, hashtags=None, album_id=None))
    it = _get(ddb, "MEDIA#900001")
    assert not [k for k, v in it.items() if "NULL" in v]
    assert {"description", "hashtags", "album_id"}.isdisjoint(it)


def test_upsert_serialises_lists_as_l_of_s_and_bools(ddb):
    dynamo.upsert(ddb, _media(hashtags=["ARCHEVT", "ArchersNetwork"]))
    assert _get(ddb, "MEDIA#900001")["hashtags"] == {"L": [{"S": "ARCHEVT"},
                                                          {"S": "ArchersNetwork"}]}


def test_cms_edit_survives_a_reload(ddb):
    """Spec §8 regression: every CMS-owned attribute is intact after the loader rewrites."""
    dynamo.upsert(ddb, _media())
    _cms(ddb, "MEDIA#900001",
         "SET overrides = :o, is_featured = :f, updated_at = :u, updated_by = :b, "
         "category_id = :c, GSI3PK = :g3, GSI3SK = :g3s",
         {":o": {"M": {"description": {"S": "CMS text"}}}, ":f": {"BOOL": True},
          ":u": {"S": T1}, ":b": {"S": "editor-1"}, ":c": {"S": "cat-1"},
          ":g3": {"S": "FEATURED"}, ":g3s": {"S": "2026-07-01T00:00:00Z"}})
    before = _get(ddb, "MEDIA#900001")
    dynamo.upsert(ddb, _media(description="second", loaded=T2))
    after = _get(ddb, "MEDIA#900001")
    for k in ("overrides", "is_featured", "updated_at", "updated_by", "category_id",
              "GSI3PK", "GSI3SK"):
        assert after[k] == before[k], k
    assert after["description"]["S"] == "second"


def test_tombstone_wins_and_leaves_the_item_untouched(ddb):
    dynamo.upsert(ddb, _media())
    _cms(ddb, "MEDIA#900001", "SET deleted_at = :d", {":d": {"S": T1}})
    before = _get(ddb, "MEDIA#900001")
    assert dynamo.upsert(ddb, _media(description="resurrect", loaded=T2)) == "skipped_deleted"
    assert _get(ddb, "MEDIA#900001") == before


def test_upsert_reraises_other_client_errors(ddb, monkeypatch):
    def boom(**_kw):
        raise ClientError({"Error": {"Code": "ProvisionedThroughputExceededException",
                                     "Message": "slow down"}}, "UpdateItem")

    monkeypatch.setattr(ddb.client, "update_item", boom)
    with pytest.raises(ClientError):
        dynamo.upsert(ddb, _media())


def test_overrides_survive_and_title_refreshes(ddb):
    """The spike's override_checks: title is L; CMS edits live in `overrides`."""
    pk = "MEDIA#900010"
    dynamo.upsert(ddb, _media(pk, description="FB cap v1", title="FB title v1"))
    _cms(ddb, pk, "SET overrides = if_not_exists(overrides, :e)", {":e": {"M": {}}})
    _cms(ddb, pk, "SET overrides.title = :t, overrides.description = :c",
         {":t": {"S": "CMS title"}, ":c": {"S": "CMS cap"}})
    dynamo.upsert(ddb, _media(pk, description=None, title="FB title v2", loaded=T2))
    it = _get(ddb, pk)
    ov = it["overrides"]["M"]
    assert it["title"]["S"] == "FB title v2"
    assert "description" not in it and ov["description"]["S"] == "CMS cap"
    assert ov["title"]["S"] == "CMS title"

    ddb.client.update_item(TableName=ddb.name, Key={"PK": {"S": pk}, "SK": {"S": "#META"}},
                           UpdateExpression="REMOVE overrides.title")
    dynamo.upsert(ddb, _media(pk, description=None, title="FB title v3", loaded=T2))
    it = _get(ddb, pk)
    assert "title" not in it["overrides"]["M"] and it["title"]["S"] == "FB title v3"


def test_cms_cannot_set_into_a_missing_overrides_map(ddb):
    """Pins the CMS gotcha (Official-Schema §5.1): create the map first."""
    dynamo.upsert(ddb, _media())
    with pytest.raises(ClientError) as exc:
        _cms(ddb, "MEDIA#900001", "SET overrides.title = :t", {":t": {"S": "CMS title"}})
    assert exc.value.response["Error"]["Code"] == "ValidationException"


# --- counts / scan_items ---------------------------------------------------------------------


def test_counts_only_count_meta_items(ddb):
    assert dynamo.counts(ddb) == {"album": 0, "media": 0}
    dynamo.upsert(ddb, _media())
    dynamo.upsert(ddb, Update("ALBUM#111", {"title": "A", "loaded_at": T1},
                              {"id": "111", "kind": "photo", "source": "fb_export",
                               "created_at": T1}))
    ddb.client.put_item(TableName=ddb.name, Item={"PK": {"S": "MEDIA#900001"},
                                                  "SK": {"S": "CREDIT#s1"}})
    ddb.client.put_item(TableName=ddb.name, Item={"PK": {"S": "STAFFER#s1"},
                                                  "SK": {"S": "#META"}})
    assert dynamo.counts(ddb) == {"album": 1, "media": 1}


def test_scan_items_returns_plain_python(ddb):
    dynamo.upsert(ddb, _media(hashtags=["ARCHEVT"]))
    _cms(ddb, "MEDIA#900001", "SET overrides = :o, is_featured = :f, n = :n",
         {":o": {"M": {"rank": {"N": "3"}, "xs": {"L": [{"N": "1"}, {"N": "1.5"}]}}},
          ":f": {"BOOL": True}, ":n": {"N": "7"}})
    ddb.client.put_item(TableName=ddb.name, Item={"PK": {"S": "MEDIA#900001"},
                                                  "SK": {"S": "CREDIT#s1"}})
    (it,) = dynamo.scan_items(ddb, "media")
    assert it["n"] == 7 and type(it["n"]) is int
    assert it["overrides"]["rank"] == 3 and type(it["overrides"]["rank"]) is int
    assert it["overrides"]["xs"] == [1, 1.5] and type(it["overrides"]["xs"][0]) is int
    assert it["hashtags"] == ["ARCHEVT"] and it["is_featured"] is True
    assert len(dynamo.scan_items(ddb)) == 2  # no filter: the edge too


def test_scan_items_filters_by_kind_and_sorts_by_pk(ddb):
    for fbid in ("c", "a", "b"):
        dynamo.upsert(ddb, _media(f"MEDIA#{fbid}"))
    dynamo.upsert(ddb, Update("ALBUM#1", {"title": "A", "loaded_at": T1},
                              {"id": "1", "kind": "photo", "source": "fb_export",
                               "created_at": T1}))
    assert [i["PK"] for i in dynamo.scan_items(ddb, "media")] == ["MEDIA#a", "MEDIA#b", "MEDIA#c"]
    assert [i["PK"] for i in dynamo.scan_items(ddb, "album")] == ["ALBUM#1"]


# --- prefetch --------------------------------------------------------------------------------


def test_prefetch_returns_only_existing_with_their_frozen_key_and_tombstone(ddb):
    dynamo.upsert(ddb, _media("MEDIA#a", path="fb-exports/x/a.jpg"))
    dynamo.upsert(ddb, _media("MEDIA#b", path="fb-exports/x/b.jpg"))
    _cms(ddb, "MEDIA#b", "SET deleted_at = :d", {":d": {"S": T1}})
    got = dynamo.prefetch(ddb, ["MEDIA#a", "MEDIA#b", "MEDIA#nope"])
    assert got == {
        "MEDIA#a": dynamo.Existing(storage_path="fb-exports/x/a.jpg", deleted=False),
        "MEDIA#b": dynamo.Existing(storage_path="fb-exports/x/b.jpg", deleted=True),
    }


def test_prefetch_of_nothing_is_empty(ddb):
    assert dynamo.prefetch(ddb, []) == {}


def test_prefetch_chunks_past_100_keys(ddb):
    pks = [f"MEDIA#{n:04d}" for n in range(150)]
    for pk in pks:
        dynamo.upsert(ddb, _media(pk))
    got = dynamo.prefetch(ddb, pks + [f"MEDIA#unknown{n}" for n in range(5)])
    assert set(got) == set(pks)


def test_prefetch_dedupes_keys(ddb):
    dynamo.upsert(ddb, _media("MEDIA#a"))
    assert set(dynamo.prefetch(ddb, ["MEDIA#a", "MEDIA#a"])) == {"MEDIA#a"}


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
            return {"Responses": {name: [{"PK": first[0]["PK"]}]},
                    "UnprocessedKeys": {name: dict(req, Keys=rest)}}
        return {"Responses": {name: [{"PK": k["PK"], "storage_path": {"S": "k"}}
                                     for k in keys]},
                "UnprocessedKeys": {}}


def test_prefetch_follows_unprocessed_keys(monkeypatch):
    monkeypatch.setattr(dynamo.time, "sleep", lambda _s: None)
    fake = _FlakyBatchGet()
    got = dynamo.prefetch(dynamo.Table(fake, "t", on_emulator=True), ["MEDIA#a", "MEDIA#b"])
    assert set(got) == {"MEDIA#a", "MEDIA#b"} and len(fake.calls) == 2
    assert got["MEDIA#b"].storage_path == "k" and got["MEDIA#a"].storage_path is None
