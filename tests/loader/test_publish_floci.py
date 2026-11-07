"""Live integration tier: one Publish, end to end, against a pinned floci over the real wire.

The env's clients are built exactly as the app builds them (`envclients`), so this proves the
floci path a curator's **Publish** takes: bucket auto-create, path-style S3, the per-type tables,
the frozen keys on a re-publish, and presigned previews that actually serve. It starts its own
container from the compose pin (never the dev one on :4566).

SKIPS CLEANLY when Docker is unreachable. Read the skip count: a skipped test is not a pass.
"""

import urllib.request
import uuid

import pytest
from conftest import floci_image

from archivenetwork.loader import dynamo, envclients
from archivenetwork.loader.envs import Env
from archivenetwork.loader.publish import publish

floci = pytest.importorskip("floci", reason="testcontainers-floci is not installed")


@pytest.fixture(scope="module")
def floci_conn():
    image = floci_image()
    if image is None:
        pytest.skip("docker-compose.yml pins no floci tag; refusing to pull latest")
    try:
        container = floci.FlociContainer(image=image)
        container.start()
    except Exception as exc:  # daemon down, image pull failure, socket permissions…
        pytest.skip(f"floci container unavailable (is Docker running?): {exc}")
    try:
        get_region = getattr(container, "get_region", None)
        region = get_region() if get_region else "us-east-1"
        yield container.get_endpoint(), region
    finally:
        container.stop()


class NoAuth:
    def session(self, env):
        raise AssertionError("a floci env must never ask for an AWS session")


def test_publish_twice_on_floci(floci_conn, ready_root):
    endpoint, region = floci_conn
    env = Env(
        name="local", kind="floci", label="Local", region=region,
        s3_bucket="publish-e2e", table_prefix=f"archivenetwork-pub-{uuid.uuid4().hex[:8]}",
        endpoint_url=endpoint,
    )
    auth = NoAuth()
    tables = envclients.tables_for(env, auth)
    storage = envclients.storage_for(env, auth)
    identity = envclients.identity_for(env, auth)
    dynamo.create_tables(tables)
    try:
        first = publish(ready_root, "ws-e2e", env, storage, tables, identity)
        assert first.ok is True, first.as_dict()
        assert first.publish.files_stored > 0

        second = publish(ready_root, "ws-e2e", env, storage, tables, identity)
        assert second.ok is True, second.as_dict()
        assert second.publish.files_stored == 0
        assert second.publish.files_skipped == first.publish.files_stored

        media = dynamo.scan_items(tables, "media")
        assert media
        for item in media:
            url = storage.presign(item["storage_path"])
            with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310 (local emulator)
                assert resp.status == 200
                assert resp.read()
    finally:
        dynamo.delete_tables(tables)
