#!/bin/bash
# Cloudflare quick tunnel under launchd (D14). Waits for the backend, then
# tunnels it. NOTE: the public URL changes every time this (re)starts —
# read the current one with ops/tunnel-url.sh.
DEVVOL="/Volumes/RecipesDev"
for i in $(seq 1 60); do
  curl -sf -o /dev/null http://localhost:8000/health && break
  sleep 2
done
exec "$DEVVOL/bin/cloudflared" tunnel --url http://localhost:8000 \
  --logfile "$DEVVOL/caches/logs/cloudflared.log"
