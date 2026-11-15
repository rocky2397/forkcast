#!/bin/bash
# Regenerate the README screenshots (docs/screenshots/) and run the
# accessibility check, against a throwaway demo kitchen.
#
# Builds the frontend, starts the backend on a fresh temporary data dir with
# the given corpus, seeds the demo kitchen through the API, drives the UI in
# the installed Google Chrome, then stops the server and deletes the data dir.
# Needs Google Chrome, Node (frontend/node_modules installed) and the backend's
# Python environment with the Epicure weights cached.
#
# With ffmpeg installed it also records the walkthrough, docs/screenshots/demo.gif.
#
# Usage:  ops/screenshots.sh [corpus.db]     (default: data/corpus.db)
set -euo pipefail

cd "$(dirname "$0")/.."
CORPUS="$(cd "$(dirname "${1:-data/corpus.db}")" && pwd)/$(basename "${1:-data/corpus.db}")"
PORT="${FORKCAST_SHOT_PORT:-8799}"
PY="${PYTHON:-$( [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3 )}"
case "$PY" in /*) PY_ABS="$PY" ;; */*) PY_ABS="$PWD/$PY" ;; *) PY_ABS="$(command -v "$PY")" ;; esac

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

for _ in $(seq 1 60); do
  curl -fs "http://localhost:$PORT/health" >/dev/null 2>&1 && break
  sleep 1
done
curl -fs "http://localhost:$PORT/health" >/dev/null || { echo "backend did not start"; exit 1; }

# The progress screens need weeks of history the API can't backdate: the
# screenshot script writes sample personas (D43) straight into the database.
(cd frontend && FORKCAST_SHOT_DB="$DATA/forkcast.db" FORKCAST_SHOT_PY="$PY_ABS" \
  node scripts/screenshots.mjs "http://localhost:$PORT" ../docs/screenshots "$DATA/video")

# The walkthrough GIFs for the README: 12 fps, 360 px wide, one shared palette.
if command -v ffmpeg >/dev/null; then
  for gif in demo progress; do
    ffmpeg -loglevel error -y -f concat -safe 0 -i "$DATA/video/$gif/frames.txt" -vf \
      "fps=12,scale=360:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" \
      "docs/screenshots/$gif.gif"
    echo "  $gif.gif ($(du -h "docs/screenshots/$gif.gif" | cut -f1))"
  done
else
  echo "  ffmpeg not found: skipped the GIFs"
fi
