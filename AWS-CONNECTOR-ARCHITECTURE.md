# AWS Architecture & Connectors

ARCHiveNetwork is designed with a decoupled architecture for AWS services. Infrastructure components (Object Storage via S3, Relational Database via PostgreSQL RDS) are abstracted behind backend interfaces and environment configuration so that local development and cloud production use identical data schemas and business logic.

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
- **`GET /api/s3/status`**: Returns `{"enabled": true, "bucket": "...", "region": "..."}` or `{"enabled": false}`. It reads local settings only and **never contacts AWS**, so `enabled: true` says nothing about whether the credentials or the bucket actually work.
- **`POST /api/s3/upload`**: Triggers `upload_ready()` for the active session's workspace. Responses:

| Status | Cause | Body / detail |
| :--- | :--- | :--- |
| `200` | The run completed — **including a run where every file failed** | `{uploaded, skipped, orphans[], errors[], bucket, region}` |
| `404` | S3 not configured (`s3_bucket` unset) | `"S3 is not configured (set ARCHIVENETWORK_S3_BUCKET)"` |
| `404` | **No export loaded** in the session — a *different* cause, same status | `"No export loaded"` |
| `409` | The workspace has never been built | `"This workspace has not been built yet — run Build first."` |
| `502` | Whole-run blocker raised by the preflight (bad creds, missing bucket, no network, missing `s3:ListBucket`) | `"S3 not reachable: ..."` |

> **`200` does not mean the bucket is complete.** Partial failure is the normal shape: a
> permissions error on a subset of keys returns `200` with `uploaded: 0` and a populated
> `errors` list. A client that treats `res.ok` as success will report "Upload complete" for a
> build that reached the bucket zero times — **always inspect `errors` and `orphans`**. Likewise,
> the two `404` causes are indistinguishable by status alone, so branch on `detail` before
> telling a user to go set `ARCHIVENETWORK_S3_BUCKET` when the real fix is to open a workspace.

### Frontend & UI Integration
- **API Layer**: Client functions `s3Status()` and `uploadToS3()` in [frontend/src/lib/api.js](frontend/src/lib/api.js#L504-L520).
- **Developer Panel**: [frontend/src/lib/components/DevPanel.svelte](frontend/src/lib/components/DevPanel.svelte#L50-L61) queries `/api/s3/status` on mount and exposes an **"Upload to S3"** action button.

### Testing Strategy
- [tests/loader/test_storage_s3.py](tests/loader/test_storage_s3.py): Tests `S3Storage` `put()`, `exists()`, `ensure_ready()`, and MIME type guessing using `moto`.
- [tests/loader/test_upload.py](tests/loader/test_upload.py): Validates `upload_ready()` against S3.
- [tests/web/test_s3_routes.py](tests/web/test_s3_routes.py): Verifies status and upload API endpoints.

---

## 2. AWS RDS Connector (PostgreSQL Database) — *Planned / Future Integration*

*To be documented once integrated.*
