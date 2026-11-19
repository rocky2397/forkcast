# Forkcast public demo on Hugging Face Spaces (D32).
#
# This file and README.md are the whole Space. It builds Forkcast from the
# public GitHub repo at one fixed commit, the same way the main Dockerfile does,
# and starts it in demo mode: every visitor gets a private copy of the demo
# kitchen. Photo and label scanning work only when the Space has an
# ANTHROPIC_API_KEY secret (D38): a pay-per-use key with a spending limit,
# capped at 10 scans per visitor and 200 a day. No other secret is used.
#
# To put a newer Forkcast online, change FORKCAST_COMMIT to a commit on main.

ARG FORKCAST_COMMIT=a2f255ee84252c5ac80d6a4223d71adf3eb3d70e

# ---- 1. Source at the pinned commit -----------------------------------------
FROM python:3.12-slim AS source
ARG FORKCAST_COMMIT
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN mkdir /src \
 && curl -fsSL "https://github.com/rocky2397/forkcast/archive/${FORKCAST_COMMIT}.tar.gz" \
  | tar -xz --strip-components=1 -C /src

# ---- 2. Frontend bundle -----------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /build
COPY --from=source /src/frontend/ ./
RUN npm ci && npm run build

# ---- 3. Runtime -------------------------------------------------------------
FROM python:3.12-slim

# Spaces run the container as user 1000 and send traffic to port 7860.
# Visitors' live kitchens are in /tmp. Two things go to /data, where a private
# storage bucket is mounted so they survive restarts: saved copies of changed
# kitchens (D34, deleted 30 days after the last visit) and anonymous usage
# totals (D33). Without a bucket both still work but reset on restart.
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf \
    FORKCAST_DEMO=1 \
    FORKCAST_DATA_DIR=/tmp/forkcast \
    FORKCAST_CORPUS_DB=/opt/forkcast/corpus.db \
    FORKCAST_STATS_DIR=/data/forkcast-stats \
    FORKCAST_KITCHENS_DIR=/data/forkcast-kitchens \
    PORT=7860

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /data && chmod a+rwx /data

COPY --from=source /src/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Epicure weights (CC BY 4.0), baked in so a start needs no network.
RUN python -c "\
from huggingface_hub import snapshot_download; \
[snapshot_download(m) for m in ('Kaikaku/epicure-cooc','Kaikaku/epicure-core','Kaikaku/epicure-chem')]" \
 && chmod -R a+rwX /opt/hf

# The public recipe corpus (~130 MB, read-only), from its GitHub release.
ARG CORPUS_URL=https://github.com/rocky2397/forkcast-corpus/releases/download/corpus-20261115-d35/corpus.db
RUN mkdir -p /opt/forkcast \
 && curl -fsSL --retry 3 -o /opt/forkcast/corpus.db "$CORPUS_URL" \
 && python -c "\
import sqlite3,sys; \
n=sqlite3.connect('file:/opt/forkcast/corpus.db?mode=ro', uri=True).execute('SELECT COUNT(*) FROM recipes').fetchone()[0]; \
print(f'corpus ok: {n:,} recipes'); \
sys.exit(0 if n else 'corpus has no recipes')"

COPY --from=source /src/backend/ ./backend/
COPY --from=frontend /build/dist ./frontend/dist

# /health reports what is running, so ops/check_live.py can confirm a deploy.
ARG FORKCAST_COMMIT
ENV FORKCAST_COMMIT=${FORKCAST_COMMIT} \
    FORKCAST_CORPUS_URL=${CORPUS_URL}

# Everything is local from here on.
ENV HF_HUB_OFFLINE=1

EXPOSE 7860
# --no-proxy-headers: the request log shows Hugging Face's proxy, never a
# visitor's IP address (D33). The demo has no login to rate-limit per visitor.
CMD ["sh", "-c", "uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT} --no-proxy-headers"]
