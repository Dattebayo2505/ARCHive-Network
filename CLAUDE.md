# CLAUDE.md

Local **FastAPI (uv)** tool that curates a weekly Facebook "Download Your Information"
export into a filtered, ready-to-upload folder. Curation only — S3 upload + Postgres load
are downstream phases (see the sibling `this_profile's_activity_across_facebook/` repo's
`PLAN.md` + `docs/ArchersNetworkEERD.md`). Design + plan live in `docs/superpowers/`.

## Commands
- `UV_LINK_MODE=copy uv run streamlinify` — run the JSON API (http://127.0.0.1:8000)
- `UV_LINK_MODE=copy uv run --no-sync pytest -q` — run backend tests (skips reinstall)
- `uv run ruff check .` — lint (line-length 100; E501 not enforced)
- `cd frontend && npm install && npm run dev` — run the SvelteKit UI (http://localhost:5173)
- `cd frontend && npm run build && node build` — production UI server (http://localhost:3000)
- `cd frontend && npm run test` — frontend Vitest unit tests

## Environment gotchas (Windows)
- Bare `python` is a broken uv shim — always use `uv run`.
- uv installs intermittently fail with `os error 32` (Defender locks the console-script
  trampoline). Prefix every uv command with `UV_LINK_MODE=copy`; use `--no-sync` for tests
  (src is on pythonpath, so no install needed); retry `uv sync` a few times for real installs.
- Project is an **editable** install from `src/streamlinify/` — never goes stale once installed.
- Frontend needs Node 20+. From `frontend/`: `npm install` once, then `npm run dev`. The UI reads
  `VITE_API_BASE` (default `http://127.0.0.1:8000`); both servers must run together.

## Architecture (modularize per functionality)
- `src/streamlinify/` package, src layout. One module = one job: `ingest/` (unzip+validate),
  `inventory/` (models, text, parser), `thumbnails/`, `selection/` (policy + state),
  `transform/` (builder + report), `web/` (thin JSON routers + serializers).
- Business logic lives in the modules; `web/` routers stay thin. `app.py` = `create_app()` factory only.
- UI is a separate **SvelteKit** app in `frontend/` (Svelte 5, Skeleton v3 on Tailwind v4,
  `adapter-node`) talking to FastAPI over a JSON API. `web/` routers are now a thin **JSON API**
  under `/api` (+ `/api/thumb/{fbid}` images) with CORS; no server-rendered HTML. The ≤10/album cap
  is still enforced **server-side** (the `409` response). Two servers run together (API :8000, UI :3000/:5173).

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
