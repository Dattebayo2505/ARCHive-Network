# Streamlinify — Archers Network FB Export Curation Tool

Local FastAPI tool that turns a weekly Facebook export into a curated,
filtered "ready-to-upload" folder. See the design + plan in `docs/superpowers/`.

## Run

Two servers run together.

```bash
# 1) API
UV_LINK_MODE=copy uv run streamlinify        # http://127.0.0.1:8000

# 2) UI (dev)
cd frontend && npm install && npm run dev     # http://localhost:5173
# UI (prod): cd frontend && npm run build && node build   # http://localhost:3000
```

> On Windows, if `uv` hits a temp-file lock during install, prefix commands with
> `UV_LINK_MODE=copy`. The UI needs Node 20+ and reads `VITE_API_BASE` (default the API above).

## Test

```bash
UV_LINK_MODE=copy uv run --no-sync pytest -q
uv run ruff check .
cd frontend && npm run test
```

## Workflow

1. Start both servers; open the UI.
2. Drop the weekly export `.zip` (or paste the unzipped folder path).
3. Pick ≤10 photos per named album; non-album photos are auto-kept.
4. Click **Build ready folder** → output lands in `workspace/ready/<export-name>/`.
   The original export is never modified.
