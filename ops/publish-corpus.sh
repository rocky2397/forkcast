#!/bin/bash
# Publish data/corpus.db as a GitHub Release asset so the Docker build can
# fetch it without credentials (D15).
#
# The app repo is private, and Render warns against putting tokens in Docker
# build args — so the corpus goes to a separate *public* data repo. It contains
# nothing private: recipes derived from the public RecipeNLG-family corpus,
# normalized against the public Epicure vocabulary.
#
# Usage:  ops/publish-corpus.sh [tag]        (default tag: corpus-YYYYMMDD)
set -euo pipefail

DATA_REPO="${FORKCAST_DATA_REPO:-rocky2397/forkcast-corpus}"
CORPUS="data/corpus.db"
TAG="${1:-corpus-$(date +%Y%m%d)}"

cd "$(dirname "$0")/.."

[ -f "$CORPUS" ] || {
  echo "No $CORPUS — build it first:"
  echo "  python backend/scripts/split_corpus.py"
  exit 1
}

if ! gh repo view "$DATA_REPO" >/dev/null 2>&1; then
  echo "Public data repo $DATA_REPO does not exist. Create it with:"
  echo "  gh repo create $DATA_REPO --public -d 'Forkcast recipe corpus releases'"
  exit 1
fi

echo "Uploading $(du -h "$CORPUS" | cut -f1) to $DATA_REPO@$TAG ..."
gh release create "$TAG" "$CORPUS" \
  --repo "$DATA_REPO" \
  --title "Recipe corpus $TAG" \
  --notes "Normalized recipe corpus for Forkcast. Read-only; baked into the deploy image." \
  2>/dev/null \
  || gh release upload "$TAG" "$CORPUS" --repo "$DATA_REPO" --clobber

echo
echo "Set this as FORKCAST_CORPUS_URL on the Render service:"
echo "  https://github.com/$DATA_REPO/releases/download/$TAG/corpus.db"
