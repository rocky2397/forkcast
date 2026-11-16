#!/bin/bash
# The browser smoke test (frontend/e2e/smoke.mjs): a first visit, end to end.
#
# Builds the frontend, starts the backend on a fresh temporary data dir with
# the given corpus, runs the test in the installed Google Chrome, then stops
# the server and deletes the data dir. CI runs this on every push; locally it
# needs Chrome, Node (frontend/node_modules installed) and the backend's
# Python environment with the Epicure weights cached.
#
# Usage:  ops/e2e.sh [corpus.db] [failure-dir]   (default: data/corpus.db, e2e-failure)
set -euo pipefail

cd "$(dirname "$0")/.."
CORPUS="$(cd "$(dirname "${1:-data/corpus.db}")" && pwd)/$(basename "${1:-data/corpus.db}")"
FAIL_DIR="$(mkdir -p "${2:-e2e-failure}" && cd "${2:-e2e-failure}" && pwd)"
PORT="${FORKCAST_E2E_PORT:-8798}"
PY="${PYTHON:-$( [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3 )}"

[ -f "$CORPUS" ] || { echo "No corpus at $CORPUS (see README: Running it)"; exit 1; }

DATA="$(mktemp -d)"
cleanup() {
  [ -n "${SERVER:-}" ] && kill "$SERVER" 2>/dev/null || true
  rm -rf "$DATA"
}
trap cleanup EXIT

(cd frontend && npm run build --silent >/dev/null)

FORKCAST_DATA_DIR="$DATA" FORKCAST_CORPUS_DB="$CORPUS" \
  "$PY" -m uvicorn app.main:app --app-dir backend --port "$PORT" --log-level warning &
SERVER=$!

for _ in $(seq 1 90); do
  curl -fs "http://localhost:$PORT/health" >/dev/null 2>&1 && break
  sleep 1
done
curl -fs "http://localhost:$PORT/health" >/dev/null || { echo "backend did not start"; exit 1; }

(cd frontend && node e2e/smoke.mjs "http://localhost:$PORT" "$FAIL_DIR")
