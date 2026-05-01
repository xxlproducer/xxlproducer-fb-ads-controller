#!/usr/bin/env bash
# Dev launcher for macOS / Linux.
set -euo pipefail
cd "$(dirname "$0")"

# --- backend setup ---
if [ ! -d backend/.venv ]; then
  echo "[setup] creating Python venv..."
  (cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -q --upgrade pip && pip install -q -r requirements.txt)
fi

# --- frontend setup ---
if [ ! -d frontend/node_modules ]; then
  echo "[setup] installing frontend deps..."
  (cd frontend && npm install)
fi

# --- run both ---
echo
echo "Starting FB Ads Controller..."
echo "  Backend  : http://127.0.0.1:8080"
echo "  Frontend : http://localhost:5173"
echo

cleanup() {
  kill "${BACKEND_PID:-0}" "${FRONTEND_PID:-0}" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(
  cd backend
  source .venv/bin/activate
  exec uvicorn app.main:app --host 127.0.0.1 --port 8080
) &
BACKEND_PID=$!

(
  cd frontend
  exec npm run dev
) &
FRONTEND_PID=$!

wait
