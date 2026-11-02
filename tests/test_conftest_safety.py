"""The test fixtures must never target the table the app actually runs on.

The old Postgres fixture connected straight to the configured database, so a plain
`pytest -q` wiped the dev database and left fixture rows behind that pointed at a `tmp_path`
store pytest later deleted. The DynamoDB fixtures keep the lesson: a derived `-test` table only.
"""

import conftest

# --- DynamoDB: the moto `ddb` fixture must never name the configured table. ---


def test_scratch_table_never_names_the_configured_table(monkeypatch):
    monkeypatch.setenv("ARCHIVENETWORK_DYNAMODB_TABLE", "archers-network-dev")
    assert conftest._scratch_table() == "archers-network-dev-test"


def test_scratch_table_has_a_default_when_unconfigured(monkeypatch):
    monkeypatch.delenv("ARCHIVENETWORK_DYNAMODB_TABLE", raising=False)
    assert conftest._scratch_table().endswith(conftest.TEST_TABLE_SUFFIX)


def test_ddb_targets_the_scratch_table_inside_moto(ddb):
    assert ddb.name.endswith(conftest.TEST_TABLE_SUFFIX)
    # moto intercepts the regional AWS host; the configured floci endpoint is never dialled.
    assert ddb.client.meta.endpoint_url.startswith("https://dynamodb.")


def test_ddb_starts_empty(ddb):
    assert ddb.client.scan(TableName=ddb.name)["Count"] == 0
