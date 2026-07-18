#!/bin/bash
# Forkcast dev environment (D10/D11: everything stays on the external SSD).
# Usage:  source dev.sh     (from anywhere; mounts the dev volume if needed)

SPARSEBUNDLE="/Volumes/Extreme SSD/RecipesDev.sparsebundle"
DEVVOL="/Volumes/RecipesDev"

if [ ! -d "$DEVVOL" ]; then
  echo "Mounting dev volume..."
  hdiutil attach "$SPARSEBUNDLE" >/dev/null || { echo "Mount failed — is the SSD plugged in?"; return 1; }
fi

# Secrets (gitignored .env: ANTHROPIC_AUTH_TOKEN for vision intake)
if [ -f "$DEVVOL/forkcast/.env" ]; then
  set -a; source "$DEVVOL/forkcast/.env"; set +a
fi

# Keep every cache off the internal disk (D10)
export HF_HOME="$DEVVOL/caches/huggingface"
export PIP_CACHE_DIR="$DEVVOL/caches/pip"
export npm_config_cache="$DEVVOL/caches/npm"

cd "$DEVVOL/forkcast" || return 1
[ -d .venv ] && source .venv/bin/activate

echo "Forkcast dev env ready at $(pwd)"
