# CLAUDE.md

Local **FastAPI (uv)** tool that curates a weekly Facebook "Download Your Information"
export into a filtered, ready-to-upload folder. Curation only — S3 upload + Postgres load
are downstream phases (see the sibling `this_profile's_activity_across_facebook/` repo's
`PLAN.md` + `docs/ArchersNetworkEERD.md`). Design + plan live in `docs/superpowers/`.

## Commands
- `UV_LINK_MODE=copy uv run streamlinify` — run the app (http://127.0.0.1:8000)
- `UV_LINK_MODE=copy uv run --no-sync pytest -q` — run tests (skips reinstall)
- `uv run ruff check .` — lint (line-length 100; E501 not enforced)

## Environment gotchas (Windows)
- Bare `python` is a broken uv shim — always use `uv run`.
- uv installs intermittently fail with `os error 32` (Defender locks the console-script
  trampoline). Prefix every uv command with `UV_LINK_MODE=copy`; use `--no-sync` for tests
  (src is on pythonpath, so no install needed); retry `uv sync` a few times for real installs.
- Project is an **editable** install from `src/streamlinify/` — never goes stale once installed.

## Architecture (modularize per functionality)
- `src/streamlinify/` package, src layout. One module = one job: `ingest/` (unzip+validate),
  `inventory/` (models, text, parser), `thumbnails/`, `selection/` (policy + state),
  `transform/` (builder + report), `web/` (thin routers + Jinja2/Alpine templates).
- Business logic lives in the modules; `web/` routers stay thin. `app.py` = `create_app()` factory only.
- UI is Jinja2 + Alpine.js (CDN), no build step. The ≤10/album cap is enforced **server-side**.

## FB-export data rules (the parser depends on these)
- Resolve media `uri` by taking the substring from `posts/` onward (strip the export-folder prefix).
- Decode mojibake on all human text: `s.encode("latin-1").decode("utf-8")`, fall back to raw.
- Photo fbid = filename stem; album fbid = trailing id (after last `_`) of the media subdir.
- **Never glob `posts/media/`** (~875 MB) — drive off the JSON, then verify the specific file exists.
- Named `album/*.json` get the ≤10 cap; everything else is "non-album" (kept, currently read-only —
  `selection/policy.py` isolates this rule so it can change later).

## Testing
- TDD. `pytest`, one test file per module, against the **synthetic fixture** (`tests/conftest.py`
  `export_root`) — never the real export. Web routes tested via FastAPI `TestClient`.

## Output contract
- Build writes a filtered mirror to `workspace/ready/<export-name>/` (gitignored). The original
  export is **read-only**, never modified.
