#!/usr/bin/env bash
# run.sh — launch the FastAPI backend and the SvelteKit dev server together
# (the macOS/Linux counterpart to run.ps1). Ctrl+C stops both.
#
# Backend runner is auto-detected: uv if installed, else the `archivenetwork`
# console script (from `pip install -e .`), else `python -m archivenetwork`.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Helper to find a free TCP port starting from a given port
get_free_port() {
  local start_port="$1"
  if command -v python3 >/dev/null 2>&1; then
    python3 -c '
import socket, sys
port = int(sys.argv[1])
while True:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", port))
        s.close()
        print(port)
        break
    except OSError:
        port += 1
' "$start_port"
  elif command -v python >/dev/null 2>&1; then
    python -c '
import socket, sys
port = int(sys.argv[1])
while True:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", port))
        s.close()
        print(port)
        break
    except OSError:
        port += 1
' "$start_port"
  elif command -v node >/dev/null 2>&1; then
    node -e '
const net = require("net");
let port = parseInt(process.argv[1], 10);
function testPort(p) {
  const server = net.createServer();
  server.once("error", () => testPort(p + 1));
  server.once("listening", () => {
    server.close(() => console.log(p));
  });
  server.listen(p, "127.0.0.1");
}
testPort(port);
' "$start_port"
  else
    echo "$start_port"
  fi
}

# Environment and port configuration
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"

if [[ -z "${ARCHIVENETWORK_PORT:-}" ]]; then
  export ARCHIVENETWORK_PORT="$(get_free_port 8000)"
fi
backend_port="$ARCHIVENETWORK_PORT"

if [[ -z "${VITE_API_BASE:-}" ]]; then
  export VITE_API_BASE="http://127.0.0.1:${backend_port}"
fi

frontend_port="$(get_free_port 5173)"
ports=("$backend_port" "$frontend_port")

if command -v uv >/dev/null 2>&1; then
  backend_cmd=(uv run archivenetwork)
elif command -v archivenetwork >/dev/null 2>&1; then
  backend_cmd=(archivenetwork)
elif command -v python3 >/dev/null 2>&1; then
  backend_cmd=(python3 -m archivenetwork)
else
  backend_cmd=(python -m archivenetwork)
fi

backend_pid=""
frontend_pid=""

# Recursively kill a process tree
kill_tree() {
  local pid="$1"
  local sig="${2:-TERM}"
  [[ -z "$pid" ]] && return 0

  if command -v pgrep >/dev/null 2>&1; then
    local children=""
    children=$(pgrep -P "$pid" 2>/dev/null || true)
    for child in $children; do
      kill_tree "$child" "$sig"
    done
  elif command -v pkill >/dev/null 2>&1; then
    pkill -"$sig" -P "$pid" 2>/dev/null || true
  fi

  # Signal the pid directly, avoiding negative PID process group kills
  kill -"$sig" "$pid" 2>/dev/null || true
}

# Backstop: free ports if any orphaned process remains
free_port() {
  local port="$1"
  [[ -z "$port" ]] && return 0

  if command -v lsof >/dev/null 2>&1; then
    local pids=""
    pids=$(lsof -ti "tcp:$port" 2>/dev/null || lsof -ti ":$port" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
      echo "$pids" | xargs kill -9 2>/dev/null || true
    fi
  elif command -v fuser >/dev/null 2>&1; then
    fuser -k "$port/tcp" 2>/dev/null || true
  elif command -v npx >/dev/null 2>&1; then
    npx --yes kill-port "$port" >/dev/null 2>&1 || true
  fi
}

cleanup() {
  trap - EXIT INT TERM
  echo
  echo "Shutting down..."

  if [[ -n "$backend_pid" ]]; then
    kill_tree "$backend_pid" TERM
  fi
  if [[ -n "$frontend_pid" ]]; then
    kill_tree "$frontend_pid" TERM
  fi

  # Allow processes a moment to exit gracefully
  for _ in 1 2 3 4 5; do
    if (! kill -0 "$backend_pid" 2>/dev/null) && (! kill -0 "$frontend_pid" 2>/dev/null); then
      break
    fi
    sleep 0.2 2>/dev/null || sleep 1
  done

  # Force kill if still running
  if [[ -n "$backend_pid" ]] && kill -0 "$backend_pid" 2>/dev/null; then
    kill_tree "$backend_pid" 9
  fi
  if [[ -n "$frontend_pid" ]] && kill -0 "$frontend_pid" 2>/dev/null; then
    kill_tree "$frontend_pid" 9
  fi

  # Backstop: ensure dev ports are released
  for port in "${ports[@]}"; do
    free_port "$port"
  done

  wait 2>/dev/null || true
  echo "Stopped backend + frontend."
}
trap cleanup EXIT INT TERM

echo "Starting backend  (${backend_cmd[*]} -> http://127.0.0.1:$backend_port)"
( cd "$root" && exec "${backend_cmd[@]}" ) &
backend_pid=$!

echo "Starting frontend (npm run dev -> http://localhost:$frontend_port)"
( cd "$root/frontend" && exec npm run dev -- --port "$frontend_port" --strictPort ) &
frontend_pid=$!

echo
echo "Both running. Press Ctrl+C to stop both."

# Portable supervision loop (compatible with macOS Bash 3.2)
while true; do
  if ! kill -0 "$backend_pid" 2>/dev/null; then
    break
  fi
  if ! kill -0 "$frontend_pid" 2>/dev/null; then
    break
  fi
  sleep 1 &
  wait $! 2>/dev/null || true
done
