#!/bin/bash
# Forkcast backend under launchd (D14): mounts the dev volume if needed,
# loads env, keeps the Mac awake while running (caffeinate -s, AC power).
set -e
DEVVOL="/Volumes/RecipesDev"
if [ ! -d "$DEVVOL/forkcast" ]; then
  hdiutil attach "/Volumes/Extreme SSD/RecipesDev.sparsebundle" || diskutil mount RecipesDev
  for i in $(seq 1 10); do [ -d "$DEVVOL/forkcast" ] && break; sleep 1; done
fi
cd "$DEVVOL/forkcast"
set -a; source .env; set +a
export HF_HOME="$DEVVOL/caches/huggingface"
# --proxy-headers: cloudflared connects from 127.0.0.1, so without it every
# login attempt shares one rate-limit bucket instead of one per real caller.
exec /usr/bin/caffeinate -s .venv/bin/uvicorn app.main:app --app-dir backend \
  --port 8000 --proxy-headers
