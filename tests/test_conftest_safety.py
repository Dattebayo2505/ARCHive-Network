"""The test fixtures must never target the tables the app actually runs on.

The old Postgres fixture connected straight to the configured database, so a plain
`pytest -q` wiped the dev database and left fixture rows behind that pointed at a `tmp_path`
store pytest later deleted. The DynamoDB fixtures keep the lesson: a derived `-test` prefix only.
"""

import conftest

from archivenetwork.loader import dynamo

# --- DynamoDB: the moto `ddb` fixture must never name a configured table. ---


def test_scratch_prefix_never_names_a_configured_table(monkeypatch):
    monkeypatch.setenv("ARCHIVENETWORK_DYNAMODB_TABLE_PREFIX", "archers-network-dev")
    assert conftest._scratch_prefix() == "archers-network-dev-test"
    real = {f"archers-network-dev-{s.suffix}" for s in dynamo.TABLES.values()}
    scratch = {f"{conftest._scratch_prefix()}-{s.suffix}" for s in dynamo.TABLES.values()}
    assert not real & scratch


def test_scratch_prefix_has_a_default_when_unconfigured(monkeypatch):
    monkeypatch.delenv("ARCHIVENETWORK_DYNAMODB_TABLE_PREFIX", raising=False)
    assert conftest._scratch_prefix().endswith(conftest.TEST_TABLE_SUFFIX)


def test_ddb_targets_scratch_tables_inside_moto(ddb):
    assert ddb.prefix.endswith(conftest.TEST_TABLE_SUFFIX)
    # moto intercepts the regional AWS host; the configured floci endpoint is never dialled.
    assert ddb.client.meta.endpoint_url.startswith("https://dynamodb.")


def test_ddb_starts_with_all_tables_empty(ddb):
    for kind in dynamo.KINDS:
        assert ddb.client.scan(TableName=ddb.name(kind))["Count"] == 0
