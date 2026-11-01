# AWS Architecture & Connectors

ARCHiveNetwork is designed with a decoupled architecture for AWS services. Infrastructure components (Object Storage via S3, and the database, which is **DynamoDB** as of 2026-10-30, see §2) are abstracted behind backend interfaces and environment configuration so that local development and cloud production share the same business logic. The data schemas match once the DynamoDB port lands; until then, Dev Mode still runs PostgreSQL (§2).

---

## 1. AWS S3 Connector (Object Storage) — *Implemented*

S3 serves as an **on-demand object store** for the media a build ships: the **album photos** copied into the ready folder, plus one **poster still per video** (`fb-exports/<hashtag>/videos/<fbid>.jpg`).

> **What is *not* uploaded.** `upload_ready()` walks `read_ready(ready_root).media` and resolves
> each file as `ready_root / row.uri`, so nothing outside the ready folder's manifests can reach
> the bucket:
> - **Video files.** The `.mp4` is never copied into the ready folder — `builder.py` rewrites each
>   video's uri `.mp4` → `.jpg` and copies the captured still instead, so only the poster is
>   uploaded. There is no object at `fb-exports/<hashtag>/videos/<fbid>.mp4`; a video with no
>   captured still is omitted from the build entirely.
> - **Thumbnail and preview caches.** These live under `workspace/state/<id>/`, outside
>   `ready_root`, and are never read by `read_ready()`. Downstream consumers must derive their own
>   derivatives from the uploaded originals.
> - **Non-album photos.** They are `disregarded` and never built, so they never reach S3 either.
>
> None of these appear in `UploadResult` — they are absent by construction, not skipped, so a
> clean run with zero errors is consistent with none of them being in the bucket.

### Configuration & Credentials
S3 settings are defined in [src/archivenetwork/config.py](src/archivenetwork/config.py#L47-L54) via Pydantic `Settings`. S3 features remain inactive unless `s3_bucket` is explicitly set via environment variables.

| Environment Variable | Config Property | Default | Description |
| :--- | :--- | :--- | :--- |
| `ARCHIVENETWORK_S3_BUCKET` | `s3_bucket` | `None` | S3 bucket name (**Enables S3 features when set**) |
| `ARCHIVENETWORK_S3_REGION` | `s3_region` | `"ap-southeast-1"` | AWS Region |
| `ARCHIVENETWORK_S3_ACCESS_KEY_ID` | `s3_access_key_id` | `None` | Optional explicit AWS Access Key ID (**only honoured together with the secret**) |
| `ARCHIVENETWORK_S3_SECRET_ACCESS_KEY` | `s3_secret_access_key` | `None` | Optional explicit AWS Secret Access Key (**only honoured together with the key ID**) |
| `ARCHIVENETWORK_FLOCI_ENDPOINT_URL` | `floci_endpoint_url` | `"http://127.0.0.1:4566"` | Local emulator endpoint (testing target) |
| `ARCHIVENETWORK_FLOCI_BUCKET` | `floci_bucket` | `"archivenetwork-dev"` | Bucket used on the emulator; auto-created |

> **Two targets, chosen per request.** `POST /api/s3/upload` takes a **required**
> `?target=aws|floci` parameter — a forgotten parameter is a `422`, never an implicit write to
> production. `GET /api/s3/status` describes both. The floci block is independent of the AWS
> block on purpose: the switch must be usable on a machine with no AWS bucket configured, and
> real credentials must never travel to the emulator (it uses the dummy `test`/`test` pair).
> Region is shared, so the emulator's key layout is byte-identical to production's.

> **Path-style addressing is load-bearing.** When `endpoint_url` is set, the client is built
> with `Config(s3={"addressing_style": "path"})`. boto3 defaults to virtual-hosted style, which
> would resolve `http://archivenetwork-dev.127.0.0.1:4566` — a hostname that does not exist.
> Every request would fail with a DNS error that reads like the container is down, sending the
> reader after the wrong problem entirely. The same `Config` carries `connect_timeout=3`,
> `read_timeout=10` and `retries={"max_attempts": 1}`, because boto3's 60s default connect
> times its retries makes a dead endpoint read as a hung UI rather than a failed upload.

> **Auto-create is asymmetric.** `S3Storage(create_if_missing=True)` is set **only** for floci,
> which starts empty. `ensure_ready()` catches a `404`/`NoSuchBucket`/`NotFound` and creates the
> bucket; a `403` re-raises, because a permissions failure must stay diagnosable rather than be
> retried as "bucket absent". The AWS target never sets the flag — a preflight that can create a
> production bucket is the opposite of a preflight.

> **Liveness is a separate question from configuration.** `floci.enabled` is always `true` (the
> settings have defaults); `floci.reachable` comes from `storage.probe_endpoint()`, a bounded
> TCP connect. This is the same split as the Postgres pane's `server_up` vs `database_exists`,
> and for the same reason: the panel must distinguish "not configured" from "configured but
> down". The probe records no *cause* — a refused connection cannot tell Docker-off from
> container-not-started from port-occupied — but the message it feeds does name Docker, because
> that is the common case and an instruction beats a taxonomy.

> **Note on Credentials — the explicit pair is both-or-neither.** `S3Storage.__init__` guards
> with `if access_key_id and secret_access_key:`, so setting only *one* of the two silently
> **discards it** and falls back to `boto3`'s standard chain (environment variables,
> `~/.aws/credentials`, AWS SSO, or IAM roles). There is no warning on that path: on a machine
> with a stale default profile the upload succeeds against the **wrong AWS account**, and on a
> clean machine it fails as `NoCredentialsError` → a `502 "S3 not reachable"` that points at the
> bucket rather than at the half-set credential pair. Set both variables or neither.

> **Required IAM actions.** The connector needs more than `s3:PutObject`, because both the
> preflight and the idempotency check are *read* calls: `head_bucket()` requires
> **`s3:ListBucket`** (on the bucket ARN) and `head_object()` requires **`s3:GetObject`** (on
> `<bucket-arn>/fb-exports/*`). A write-only policy passes `GET /api/s3/status` — which only
> reads local settings and never contacts AWS — and then fails the preflight with a 403 rendered
> as `502 "S3 not reachable"`, even though the bucket is fine and writes would have succeeded.

### Storage Abstraction (`Storage` Protocol)
In [src/archivenetwork/loader/storage.py](src/archivenetwork/loader/storage.py#L35-L123), a Python `Protocol` defines the common interface for object storage:

```python
class Storage(Protocol):
    def key_for(self, fbid: str, hashtag: str | None, group: str, suffix: str) -> str: ...
    def exists(self, key: str) -> bool: ...
    def put(self, src: Path, key: str) -> bool: ...
    def ensure_ready(self) -> None: ...
```

- **`S3Storage`**: Implements `Storage` using `boto3.client("s3")`.
- **Key Determinism**: Both `LocalStorage` (dev) and `S3Storage` (prod) compute identical keys via `media_key()` (e.g., `fb-exports/archevt/animusika-2026/1470662168409180.jpg`) *from the same inputs*. The database stores backend-agnostic keys without hardcoding domains. This guarantees the two **backends** agree; it does **not** guarantee an uploaded key matches the key already stored in Postgres — see the freeze below.
- **The `storage_path` freeze (do not remove it)**: the key is derived from *mutable* things (the album's canonical hashtag, its name), so unlike the old date-partitioned key it is **not self-healing**. What makes it safe is that `storage_path` is deliberately absent from the `ON CONFLICT ... DO UPDATE SET` clause in `load.py`, and `load()` reuses any key already on the row: a renamed album keeps its original, *stale-but-valid* key instead of stranding its objects. (`hashtag` **is** updatable — the tag may be corrected on a re-load; the key may not.)
- **Idempotency**: `S3Storage.put()` calls `self.exists(key)` (`head_object`) before uploading. If an object already exists at that key, the upload is skipped and the file is counted under `skipped`. **This is a key-existence check only** — it compares no size, mtime or ETag, so *changed content at an existing key is never re-uploaded*. Re-capturing a video still or rebuilding a corrected image therefore leaves the bucket serving the old object, reported as `skipped` (which reads as "already correct"). Forcing a re-push means deleting the object first.
- **Preflight Check**: `ensure_ready()` performs `head_bucket()` to fail fast if credentials or bucket access are invalid. It needs `s3:ListBucket` — see *Required IAM actions* above.

### On-Demand Upload Loader
The uploader in [src/archivenetwork/loader/upload.py](src/archivenetwork/loader/upload.py#L28-L49) operates independently of Postgres:
1. Calls `storage.ensure_ready()` for preflight verification.
2. Scans the transformed build directory (`workspace/ready/<workspace_id>/`).
3. Reads media manifests via `read_ready()`.
4. Recomputes S3 object keys using `storage.key_for(...)` — **unconditionally, with no DB lookup**.
5. Uploads missing media via `storage.put(...)` and returns an `UploadResult` (`uploaded`, `skipped`, `orphans`, `errors`). Per-file failures are **swallowed into `errors`** (and a uri with no file on disk into `orphans`); one bad file never sinks the run, so a completed `UploadResult` is *not* by itself proof that everything reached the bucket.

> **The recompute can diverge from the database.** Step 4 derives the key from the *current*
> ready folder, while `load()` honours the frozen `storage_path` on an existing row. Rename an
> album (or correct its canonical hashtag), rebuild, re-load, then upload: the object lands under
> `fb-exports/<tag>/<new-slug>/<fbid>.jpg` while every DB row still points at `<old-slug>`. Both
> operations report success, but any consumer resolving images as `<cdn>/<storage_path>` 404s for
> that album, and the bucket accumulates a copy under a key nothing references. The correct
> remedy is to re-key deliberately (or leave the stale-but-valid key alone) — **not** to add
> `storage_path` to the UPSERT's UPDATE set, which would re-key and strand every object already
> uploaded under the old name.

### REST API Routes
Endpoints in [src/archivenetwork/web/routes_s3.py](src/archivenetwork/web/routes_s3.py#L57-L81) expose S3 capabilities over HTTP (mounted in FastAPI via `s3_router` in [src/archivenetwork/app.py](src/archivenetwork/app.py#L58-L68)):
- **`GET /api/s3/status`**: Returns both targets — `{"aws": {...}, "floci": {...}}`. `aws` collapses to `{"enabled": false}` when unset and reads local settings only, so it **never contacts AWS**: `enabled: true` says nothing about whether the credentials or the bucket actually work. `floci.enabled` is always `true`; only `floci.reachable` (a bounded TCP probe) reports liveness.

```json
{
  "aws":   { "enabled": true, "bucket": "archers-net", "region": "ap-southeast-1" },
  "floci": { "enabled": true, "bucket": "archivenetwork-dev", "region": "ap-southeast-1",
             "endpoint_url": "http://127.0.0.1:4566",
             "reachable": false, "reason": "connection refused" }
}
```

- **`POST /api/s3/upload?target=aws|floci`**: Triggers `upload_ready()` for the active session's workspace against the named target. Responses:

| Status | Cause | Body / detail |
| :--- | :--- | :--- |
| `200` | The run completed — **including a run where every file failed** | `{uploaded, skipped, orphans[], errors[], target, bucket, region, endpoint_url}` |
| `404` | `target=aws` and S3 not configured (`s3_bucket` unset). `target=floci` never 404s here | `"S3 is not configured (set ARCHIVENETWORK_S3_BUCKET)"` |
| `404` | **No export loaded** in the session — a *different* cause, same status | `"No export loaded"` |
| `409` | The workspace has never been built | `"This workspace has not been built yet — run Build first."` |
| `422` | **`target` missing or not one of `aws`/`floci`** — a forgotten parameter is never an implicit production write | FastAPI validation error |
| `502` | Whole-run blocker raised by the preflight (bad creds, missing bucket, no network, missing `s3:ListBucket`) | `"S3 not reachable: ..."` |
| `502` | `target=floci` and the endpoint refused the connection | The Docker message naming `docker compose up -d` and the expected endpoint |

> **Exception ordering is load-bearing.** `EndpointConnectionError` and `ConnectTimeoutError` are
> **subclasses of `BotoCoreError`**, so their `except` arm must come *first* in `upload()`. Put
> the generic arm above them and it swallows both, and the Docker message never renders — the
> user gets a bare `"S3 not reachable"` for a container that simply is not up.

> **`200` does not mean the bucket is complete.** Partial failure is the normal shape: a
> permissions error on a subset of keys returns `200` with `uploaded: 0` and a populated
> `errors` list. A client that treats `res.ok` as success will report "Upload complete" for a
> build that reached the bucket zero times — **always inspect `errors` and `orphans`**. Likewise,
> the two `404` causes are indistinguishable by status alone, so branch on `detail` before
> telling a user to go set `ARCHIVENETWORK_S3_BUCKET` when the real fix is to open a workspace.

### Frontend & UI Integration
- **API Layer**: Client functions `s3Status()` and `uploadToS3(target, fetchFn)` in [frontend/src/lib/api.js](frontend/src/lib/api.js). `target` is `uploadToS3`'s **first** parameter.
- **Target store**: [frontend/src/lib/s3target.svelte.js](frontend/src/lib/s3target.svelte.js) holds the armed target in `localStorage` (key `archive-s3-target`), defaulting to **`floci`** so a fresh browser profile is never armed at production. It also exports `canUpload(target, s3)` — the rule that gates the Upload button — which lives there rather than in the component so it is unit-testable.
- **Developer Panel**: [frontend/src/lib/components/DevPanel.svelte](frontend/src/lib/components/DevPanel.svelte) queries `/api/s3/status` on mount and renders a two-position switch (Local floci ⇄ AWS S3). The section renders **even when AWS is unconfigured** — floci is always available, so it is the AWS *position of the switch* that gets disabled. When the probe reports floci down, an amber banner names Docker and a **Re-check** button re-probes; that button is deliberately never gated on `busy` or on the probe, because it is the only way out of a disabled Upload button.

### Testing Strategy

Two tiers, because they prove different things.

- **Unit — `moto[s3]`, in-memory, always runs.** [tests/loader/test_storage_s3.py](tests/loader/test_storage_s3.py) (`put()`, `exists()`, `ensure_ready()`, MIME guessing, endpoint/path-style config, auto-create), [tests/loader/test_probe.py](tests/loader/test_probe.py), [tests/loader/test_upload.py](tests/loader/test_upload.py), [tests/web/test_s3_routes.py](tests/web/test_s3_routes.py). Fast, no Docker. moto patches botocore below the socket, so it verifies logic and key computation but **cannot** prove anything about the real wire.
- **Integration — `testcontainers-floci` + Docker.** [tests/loader/test_storage_s3_floci.py](tests/loader/test_storage_s3_floci.py) runs a real [floci](https://github.com/floci-io/floci) container and proves what moto cannot: that path-style addressing is genuinely required, that `ContentType` survives the wire, that auto-create works against a genuinely empty store, and that `upload_ready()` is idempotent across two live runs.

Start the emulator from the repo root with **`docker compose up -d`** — [docker-compose.yml](docker-compose.yml) is checked in and already binds port `4566` and persists objects under the gitignored `workspace/floci-data/`. Ad-hoc equivalent: `docker run -p 4566:4566 floci/floci:latest`. The port must match `ARCHIVENETWORK_FLOCI_ENDPOINT_URL`. On ARM hosts use the `:latest-jvm` tag.

> **Read the skip count.** The integration tier skips cleanly when floci is not installed or
> Docker is unreachable — the same philosophy as the `pg_conn` fixture. `N skipped` means those
> tests **did not run**, and a skipped test is not a passing one. Use `pytest -rs` to see why.

---

## 2. AWS DynamoDB Connector — *Decided, port pending*

**The production database is Amazon DynamoDB** (decided 2026-10-30). Aurora DSQL and RDS
PostgreSQL were considered and set aside: DynamoDB costs about $0/mo at this workload, needs no
VPC, bastion, tunnel or connection pool, and has true 35-day point-in-time recovery.

**What runs today.** The loader still reaches a database only through Dev Mode, and that
database is still PostgreSQL: psycopg 3, with a plain connection URL in
`ARCHIVENETWORK_DATABASE_URL` pointing at a local server. The port replaces it.

**The target connector:**

- **Client.** `boto3`, the same library and credential chain as the S3 connector (§1): explicit
  keys only for local work, otherwise environment, `~/.aws`, IAM Identity Center or a role. No
  connection URL, password or pool. Region `ap-southeast-1`, shared with the bucket.
- **Two targets, like S3.** An `endpoint_url` points the client at the local floci emulator
  (port `4566`, which also serves DynamoDB). Without it, the client talks to AWS. Planned
  settings: `ARCHIVENETWORK_DYNAMODB_TABLE` and `ARCHIVENETWORK_DYNAMODB_ENDPOINT_URL`, replacing
  `ARCHIVENETWORK_DATABASE_URL` as the Dev Mode gate (every `/api/dev/*` route still 404s when
  unset).
- **Tables.** `archers-network` holds the album and media items the loader writes, plus
  everything the CMS writes. `archers-network-users` holds CMS logins and is **never granted to
  the loader**.
- **Writes: `UpdateItem` only.** The loader never uses `PutItem`, `BatchWriteItem` or
  `batch_writer()`. Each of them replaces the whole item, which would silently erase every field
  the CMS has edited. Each write sets only the loader's own attributes, freezes `storage_path`
  with `if_not_exists`, and carries `attribute_not_exists(deleted_at)`, so a photo the CMS
  deleted is not brought back by the next weekly export.
- **IAM.** The curator's role gets `GetItem`, `BatchGetItem`, `Query`, `Scan`, `DescribeTable` and
  `UpdateItem` on the main table only. `UpdateItem` is meant to be narrowed to the loader's
  attributes and key prefixes (`dynamodb:Attributes`, `dynamodb:LeadingKeys`); that condition
  syntax is **unverified** until the spike. The S3 write narrows to `fb-exports/*`, because the
  CMS owns a separate `cms/` prefix.
- **Testing.** The same two tiers as §1: `moto[dynamodb]` in memory, and floci in Docker as a
  real-endpoint tier. A local spike (2026-10-30) confirmed that both honour the loader's write
  rules: `if_not_exists`, `REMOVE`, condition expressions and sorted, sparse GSIs. floci 1.7.0
  does **not** keep DynamoDB tables across a container restart once a GSI has a sort key, so a
  floci restart means re-loading. Tests never touch the configured table.

*Connector details to be documented once the port lands.*
