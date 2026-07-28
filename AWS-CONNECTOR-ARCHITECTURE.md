# AWS Architecture & Connectors

ARCHiveNetwork is designed with a decoupled architecture for AWS services. Infrastructure components (Object Storage via S3, Relational Database via PostgreSQL RDS) are abstracted behind backend interfaces and environment configuration so that local development and cloud production use identical data schemas and business logic.

---

## 1. AWS S3 Connector (Object Storage) — *Implemented*

S3 serves as an **on-demand object store** for media assets (images, videos, thumbnails, and previews).

### Configuration & Credentials
S3 settings are defined in [src/archivenetwork/config.py](src/archivenetwork/config.py#L47-L54) via Pydantic `Settings`. S3 features remain inactive unless `s3_bucket` is explicitly set via environment variables.

| Environment Variable | Config Property | Default | Description |
| :--- | :--- | :--- | :--- |
| `ARCHIVENETWORK_S3_BUCKET` | `s3_bucket` | `None` | S3 bucket name (**Enables S3 features when set**) |
| `ARCHIVENETWORK_S3_REGION` | `s3_region` | `"ap-southeast-1"` | AWS Region |
| `ARCHIVENETWORK_S3_ACCESS_KEY_ID` | `s3_access_key_id` | `None` | Optional explicit AWS Access Key ID |
| `ARCHIVENETWORK_S3_SECRET_ACCESS_KEY` | `s3_secret_access_key` | `None` | Optional explicit AWS Secret Access Key |

> **Note on Credentials:** If explicit credentials are not provided, `boto3` automatically resolves credentials using AWS's standard chain (environment variables, `~/.aws/credentials`, AWS SSO, or IAM roles).

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
- **Key Determinism**: Both `LocalStorage` (dev) and `S3Storage` (prod) compute identical keys via `media_key()` (e.g., `fb-exports/archevt/animusika-2026/1470662168409180.jpg`). The database stores backend-agnostic keys without hardcoding domains.
- **Idempotency**: `S3Storage.put()` calls `self.exists(key)` (`head_object`) before uploading. If the file already exists in the bucket, upload is skipped.
- **Preflight Check**: `ensure_ready()` performs `head_bucket()` to fail fast if credentials or bucket access are invalid.

### On-Demand Upload Loader
The uploader in [src/archivenetwork/loader/upload.py](src/archivenetwork/loader/upload.py#L28-L49) operates independently of Postgres:
1. Calls `storage.ensure_ready()` for preflight verification.
2. Scans the transformed build directory (`workspace/ready/<workspace_id>/`).
3. Reads media manifests via `read_ready()`.
4. Recomputes S3 object keys using `storage.key_for(...)`.
5. Uploads missing media via `storage.put(...)` and returns an `UploadResult` (`uploaded`, `skipped`, `orphans`, `errors`).

### REST API Routes
Endpoints in [src/archivenetwork/web/routes_s3.py](src/archivenetwork/web/routes_s3.py#L57-L81) expose S3 capabilities over HTTP (mounted in FastAPI via `s3_router` in [src/archivenetwork/app.py](src/archivenetwork/app.py#L58-L68)):
- **`GET /api/s3/status`**: Returns `{"enabled": true, "bucket": "...", "region": "..."}` or `{"enabled": false}`.
- **`POST /api/s3/upload`**: Triggers `upload_ready()` for the active session's workspace.

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
