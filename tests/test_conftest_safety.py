"""The test fixtures must never target the tables the app actually runs on.

The old Postgres fixture connected straight to the configured database, so a plain
`pytest -q` wiped the dev database and left fixture rows behind that pointed at a `tmp_path`
store pytest later deleted. The DynamoDB fixtures keep the lesson: a derived `-test` prefix only,
checked against every environment's prefix (committed and the local overlay).
"""

import conftest

from archivenetwork.config import Settings
from archivenetwork.loader import dynamo
from archivenetwork.loader.envs import load_registry


def _registry():
    s = Settings()
    return load_registry(s.environments_file, s.environments_local_file)


def test_scratch_prefix_differs_from_every_env_prefix():
    scratch = conftest._scratch_prefix()
    assert scratch == load_registry(Settings().environments_file).floci().table_prefix + "-test"
    prefixes = {env.table_prefix for env in _registry().envs.values()}
    assert scratch not in prefixes
    real = {f"{p}-{s.suffix}" for p in prefixes for s in dynamo.TABLES.values()}
    mine = {f"{scratch}-{s.suffix}" for s in dynamo.TABLES.values()}
    assert not real & mine


def test_scratch_prefix_ignores_the_retired_env_var(monkeypatch):
    monkeypatch.setenv("ARCHIVENETWORK_DYNAMODB_TABLE_PREFIX", "archers-network-dev")
    assert conftest._scratch_prefix() == "archers-network-local-test"


def test_ddb_targets_scratch_tables_inside_moto(ddb):
    assert ddb.prefix.endswith(conftest.TEST_TABLE_SUFFIX)
    # moto intercepts the regional AWS host; the configured floci endpoint is never dialled.
    assert ddb.client.meta.endpoint_url.startswith("https://dynamodb.")


def test_ddb_starts_with_all_tables_empty(ddb):
    for kind in dynamo.KINDS:
        assert ddb.client.scan(TableName=ddb.name(kind))["Count"] == 0
