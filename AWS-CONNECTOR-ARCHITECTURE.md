# AWS Architecture & Connectors

ARCHiveNetwork's Dev Mode publishes a built `ready/` folder to a **named environment**: one S3
bucket plus one set of DynamoDB tables, reached as one identity. The same code path serves the
local floci emulator and real AWS. Only the environment's *kind* (`floci` or `aws`) changes how
its clients are built. The database is **DynamoDB** (decided 2026-10-30, §3).

Design spec: `docs/superpowers/specs/2026-11-07-aws-environments-design.md` (private docs). This
file is the public summary.

---

## 1. Environments — `environments.toml` (`loader/envs.py`)

Environments are data, not code.

- **`environments.toml`** (committed) defines `local` (kind `floci`, the default), `dev` and
  `prod` (kind `aws`). The repo is public, so the AWS envs' sign-in identifiers (`start_url`,
  `account_id`) are left **empty** there.
- **`environments.local.toml`** (gitignored; start from `environments.local.toml.example`) is
  merged over it key by key. It fills in those identifiers (from the *Archers Network AWS Guide*)
  and can add personal envs. An AWS env still missing them is listed as `configured: false` and
  shown disabled, so a fresh clone runs on `local` with no setup.
- An AWS env may use `profile = "<name>"` instead of an `[sso]` table, to borrow a named AWS CLI v2
  profile.

The registry's guards:
- A broken committed file stops startup. A broken overlay (bad TOML, an invalid env, a non-UTF-8
  encoding) is ignored whole and reported, so the app still starts.
- An overlay can never turn off `prod`'s typed confirm. Any env pointed at a confirm env's bucket
  or table prefix must itself require the confirm.
- No two envs may share a bucket or prefix in the same account and region (or on the same floci
  endpoint).

`.env` holds machine settings only and is optional. The retired AWS settings
(`ARCHIVENETWORK_S3_*`, `ARCHIVENETWORK_DYNAMODB_TABLE_PREFIX`,
`ARCHIVENETWORK_DYNAMODB_ENDPOINT_URL`, `ARCHIVENETWORK_FLOCI_ENDPOINT_URL` /
`ARCHIVENETWORK_FLOCI_BUCKET`, `ARCHIVENETWORK_MEDIA_*`) are no longer read. If present, the
backend warns at startup and `GET /api/envs` lists them under `stale_settings` (names only).

## 2. Sign-in and clients (`loader/awsauth.py`, `loader/envclients.py`)

- **App-scoped IAM Identity Center sign-in.** The backend runs the OAuth device flow that
  `aws sso login` uses, through boto3's `sso-oidc` / `sso` clients. No AWS CLI is needed, and
  `~/.aws` is untouched.
  - The routes: `POST /api/envs/{name}/login` starts the flow, `GET` polls it, and
    `POST …/logout` signs out.
  - The token cache is `workspace/aws/sso/<sha1(start_url)>.json`, one per start URL, so `dev`
    and `prod` share one sign-in. It is created owner-only on POSIX. Treat it as a credential:
    its tokens can mint role keys.
  - The short-lived role keys themselves stay in memory only. They are refreshed with at least
    15 minutes left, so a presigned preview never outlives them.
  - `profile` envs skip this and use `boto3.Session(profile_name=…)`.
- **One session per environment.** `envclients.clients_for()` builds the env's `S3Storage`,
  DynamoDB `Tables` and STS identity from a single `boto3.Session`, so the bucket and the tables
  are always reached as the same identity. A floci env never touches the sign-in: it gets the
  dummy `test`/`test` pair, so real keys never travel to the emulator.
- **Errors say what to do.** An absent or expired login is `401 {"error": "signed_out"}`. A denial
  is `403 {"error": "access_denied", "detail": …}`, naming the action and resource, or the
  unassigned role and account. A network failure is a `502` saying that re-running is safe.
  Structured errors are top-level `{"error": <code>, …}` bodies (`web/envparam.py`).

## 3. Publish — `POST /api/publish?env=<name>` (`loader/publish.py`)

One click replaces the old separate *Load* and *Upload*. `env` is required: a missing or unknown
env is a `422`, never an implicit write. The request must carry a JSON body; anything else is a
`415`, which keeps a drive-by web page from triggering it. A `confirm = true` env (`prod`) needs
`{"confirm": "prod"}`, exact and case-sensitive. The Dev panel sends it only after the user types
the name; without it the server answers `409 confirm_required`. One Publish per env runs at a
time (`409 publish_running`).

1. **Preflight**: signed in (STS `get_caller_identity`), the account matches the env's
   `account_id` when one is set, the bucket answers `head_bucket`, and every probed table exists.
   Nothing is written unless all of these pass. A failed preflight is a `200` with `ok: false`.
2. **Publish** = `loader.load()` with the env's storage and tables:
   - It reads **only** the ready folder's JSON manifests (`read_ready`), so the `.mp4`s,
     thumbnail caches and disregarded non-album photos can never reach the bucket.
   - It pre-fetches existing items, uploads each object, and only then writes its item.
   - One file's S3 failure is recorded and its item is not written. A lost connection or an
     expired login stops the whole run.
3. **Verify**, scoped to this run: every published media item is in the table with a
   `storage_path`, every such object is in the bucket, every album is in the table, and the counts
   add up. A size difference is a warning, never a failure.

`ok` is true only if all three steps pass. **Re-running Publish is always safe**: existing objects
are skipped, and items are updated in place.

### S3 details (`loader/storage.py`)

- **Key:** `fb-exports/<hashtag>/<album-slug>/<fbid>.jpg` (`media_key()`), plus
  `fb-exports/<hashtag>/videos/<fbid>.jpg` for a video's poster still. The key is **frozen** on
  the item after its first insert (`if_not_exists`), so renaming an album never re-keys or strands
  its objects. A renamed album's photos keep their original, stale-but-valid key.
- **Idempotency is a key-existence check** (`head_object` before `put_object`): changed bytes at
  an existing key are never re-uploaded. First-stored bytes win, like the frozen key.
- **Path-style addressing on floci** (`addressing_style: "path"`). Virtual-hosted style would
  resolve `<bucket>.127.0.0.1`, a DNS error that reads like the container is down. All clients
  carry short connect/read timeouts.
- **Bucket auto-create is floci-only.** On AWS, the preflight never creates a bucket.
- **Previews:** the Dev panel's item browser shows each media row through a presigned GET valid
  for 15 minutes, because the buckets are private.
- **IAM the app needs on S3:** `s3:ListBucket` on the bucket (for `head_bucket` and for the 403
  vs 404 distinction), plus `s3:GetObject` and `s3:PutObject` on `<bucket>/*`.

## 4. DynamoDB (`loader/items.py`, `loader/dynamo.py`)

- **11 tables per environment, one per item type**, named `<table_prefix>-<type>`: `album`,
  `media`, `credit`, `featuring`, `staffer`, `staff-term`, `department`, `category`, `channel`,
  `service` and `users`. Their exact keys and GSIs are the contract in
  `infra/schema/dynamodb-tables.json`, and `dynamo.TABLES` mirrors it. The loader writes
  **album and media only**. The rest are CMS-written.
- **Writes are `UpdateItem` only.** The loader never uses `PutItem`, `BatchWriteItem` or
  `batch_writer()`: each replaces the whole item and would erase the CMS's edits. Each write sets
  only the loader's own attributes, freezes `storage_path`, and carries
  `attribute_not_exists(deleted_at)`, so an item the CMS deleted stays deleted.
  - **IAM does not enforce this.** One `Curators` group serves this app and the CMS, so it must
    allow the CMS's `PutItem`. The loader's code and its tests are the only guard.
- **Table admin** (`GET|POST|DELETE /api/dev/tables?env=`) creates, resets and deletes tables
  **on floci only**. On AWS it answers `409`: AWS tables are created by hand, per the AWS guide.
- **The probe** keeps "is the endpoint up?" apart from "which tables are missing?" and "did
  DynamoDB refuse?". So the panel never offers *Create tables* for what is really a permissions or
  login problem. On AWS it checks only the five tables the loader reads (album, media, credit,
  featuring, staffer); on floci, all 11.

## 5. The AWS account (built by hand)

Terraform was retired on 2026-11-07. The account is built by hand in the console, following the
*Archers Network AWS Guide* (Google Drive), which holds the real identifiers. `README.md` §
"What the AWS account must contain" lists the contract the app relies on:
- Identity Center with `Admins` and `Curators` groups;
- the `Curators` permission set scoped to both environments' tables and buckets;
- private, versioned, encrypted buckets;
- the 11 tables per prefix with PITR;
- a budget alarm.

Because the same group reaches both environments, IAM cannot stop a curator writing to `prod`.
`prod`'s typed confirm, checked in the UI and again on the server, is the safeguard.

## 6. Local emulator and testing

- **floci** (`docker compose up -d` from the repo root; port `4566` serves both S3 and DynamoDB).
  `docker-compose.yml` pins an exact image tag and persists objects under the gitignored
  `workspace/floci-data/`. The Dev panel can start, restart and stop it when Docker is usable.
- **Unit tier:** `moto` (S3 + DynamoDB) in memory, which always runs. Sign-in is tested against
  stub Identity Center clients, since moto doesn't emulate it.
- **Integration tier:** `tests/loader/test_dynamo_floci.py`, `test_storage_s3_floci.py` and
  `test_publish_floci.py` start their own throwaway floci container at the compose pin. They
  prove what moto can't (path-style addressing, `ContentType` over the wire, a real Publish run
  twice). They **skip** when Docker is unreachable, so read the skip count: a skipped test is not
  a passing one.
- Tests never touch a configured environment's tables. The fixtures use a separate `-test` prefix.
