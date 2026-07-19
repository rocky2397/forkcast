#!/bin/bash
# Print the current public demo URL.
grep -o "https://[a-z0-9-]*\.trycloudflare\.com" \
  /Volumes/RecipesDev/caches/logs/tunnel.out.log \
  /Volumes/RecipesDev/caches/logs/cloudflared.log 2>/dev/null | tail -1
