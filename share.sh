#!/bin/bash
# Public demo link (D14): Cloudflare quick tunnel to the local backend.
# Prereq: backend running on :8000 (it serves the built frontend from frontend/dist).
# The printed *.trycloudflare.com URL is random per run and dies with this
# process — demo use only. Consider backing up data/forkcast.db first:
# visitors share YOUR inventory, meal log, and taste profile.
exec /Volumes/RecipesDev/bin/cloudflared tunnel --url http://localhost:8000
