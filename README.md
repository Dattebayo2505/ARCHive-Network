# Streamlinify — Archers Network FB Export Curation Tool

Local FastAPI tool that turns a weekly Facebook export into a curated,
filtered "ready-to-upload" folder. See the design + plan in `docs/superpowers/`.

## Run

```bash
uv run streamlinify
# open http://127.0.0.1:8000
```

> On Windows, if `uv` hits a temp-file lock during install, prefix commands with
> `UV_LINK_MODE=copy` (e.g. `UV_LINK_MODE=copy uv run streamlinify`).

## Test

```bash
uv run pytest -q
uv run ruff check .
```

## Workflow

1. Drop the weekly export `.zip` (or paste the unzipped folder path).
2. Pick ≤10 photos per named album; non-album photos are auto-kept.
3. Click **Build ready folder** → output lands in `workspace/ready/<export-name>/`.
   The original export is never modified.
