"""Live integration tier: the real HTTP wire against a real floci container.

Deliberately separate from the moto tier. moto patches botocore below the socket, so it can
never prove the things that actually break against an emulator: that path-style addressing
is required, that ContentType survives the wire, or that auto-create works on a genuinely
empty store.

SKIPS CLEANLY when floci is not installed or Docker is unreachable — the same philosophy as
the `pg_conn` fixture. Read the skip count: a skipped test is not a passing one.
"""

import pytest

from archivenetwork.inventory.parser import build_inventory
from archivenetwork.loader.storage import S3Storage, probe_endpoint
from archivenetwork.loader.upload import upload_ready
from archivenetwork.transform.builder import build_ready_folder

floci = pytest.importorskip("floci", reason="testcontainers-floci is not installed")

BUCKET = "archivenetwork-itest"


@pytest.fixture(scope="module")
def floci_endpoint():
    try:
        container = floci.FlociContainer()
        container.start()
    except Exception as exc:  # daemon down, image pull failure, socket permissions…
        pytest.skip(f"floci container unavailable (is Docker running?): {exc}")
    try:
        yield container.get_endpoint()
    finally:
        container.stop()


def _store(endpoint, bucket=BUCKET, create=True):
    return S3Storage(
        bucket,
        "us-east-1",
        "test",
        "test",
        endpoint_url=endpoint,
        create_if_missing=create,
    )


def test_probe_sees_the_running_container(floci_endpoint):
    assert probe_endpoint(floci_endpoint).reachable is True


def test_ensure_ready_creates_the_bucket_on_an_empty_emulator(floci_endpoint):
    store = _store(floci_endpoint, bucket="archivenetwork-fresh")
    store.ensure_ready()
    store.ensure_ready()  # idempotent: the second call finds it and does nothing
    assert store.exists("no/such/key.jpg") is False


def test_put_survives_the_real_wire_with_its_content_type(floci_endpoint, tmp_path):
    store = _store(floci_endpoint)
    store.ensure_ready()
    src = tmp_path / "p.jpg"
    src.write_bytes(b"JPEGDATA")
    key = store.key_for("999", "ARCHEVT", "grp", ".jpg")

    assert store.put(src, key) is True
    assert store.exists(key) is True
    # moto cannot prove this: it is what the emulator actually stored.
    head = store.client.head_object(Bucket=BUCKET, Key=key)
    assert head["ContentType"] == "image/jpeg"
    # Idempotent on a real backend, not just an in-memory one.
    assert store.put(src, key) is False


def test_upload_ready_is_idempotent_across_two_live_runs(floci_endpoint, export_root, tmp_path):
    ready = tmp_path / "ready"
    inv = build_inventory(export_root)
    keep = {p.fbid for p in inv.all_photos() if not p.is_video}
    build_ready_folder(export_root, ready, keep)

    store = _store(floci_endpoint, bucket="archivenetwork-upload")
    first = upload_ready(ready, store)
    assert first.uploaded > 0
    assert first.errors == []

    second = upload_ready(ready, store)
    assert second.uploaded == 0
    assert second.skipped == first.uploaded
