#!/usr/bin/env bash
# run.sh — launch the FastAPI backend and the SvelteKit dev server together
# (the macOS/Linux counterpart to run.ps1). Ctrl+C stops both.
#
# Backend runner is auto-detected: uv if installed, else the `archivenetwork`
# console script (from `pip install -e .`), else `python -m archivenetwork`.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v uv >/dev/null 2>&1; then
  backend_cmd=(uv run archivenetwork)
elif command -v archivenetwork >/dev/null 2>&1; then
  backend_cmd=(archivenetwork)
else
  backend_cmd=(python -m archivenetwork)
fi

backend_pid=""
frontend_pid=""

cleanup() {
  echo
  echo "Shutting down..."
  [[ -n "$backend_pid" ]] && kill "$backend_pid" 2>/dev/null || true
  [[ -n "$frontend_pid" ]] && kill "$frontend_pid" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting backend  (${backend_cmd[*]} -> http://127.0.0.1:8000)"
( cd "$root" && exec "${backend_cmd[@]}" ) &
backend_pid=$!

echo "Starting frontend (npm run dev -> http://localhost:5173)"
( cd "$root/frontend" && exec npm run dev ) &
frontend_pid=$!

echo
echo "Both running. Press Ctrl+C to stop both."
# Exit as soon as either process dies so cleanup tears the other down too.
wait -n
