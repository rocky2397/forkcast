# Forkcast public demo on Hugging Face Spaces (D32).
#
# This file and README.md are the whole Space. It builds Forkcast from the
# public GitHub repo at one fixed commit, the same way the main Dockerfile does,
# and starts it in demo mode: every visitor gets a private copy of the demo
# kitchen, and photo scanning is off. No key or other secret is needed or used.
#
# To put a newer Forkcast online, change FORKCAST_COMMIT to a commit on main.

ARG FORKCAST_COMMIT=2cf6aa73e4ccbda8d75577f97e8f060f01481d99

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
# Visitors' kitchens are throwaway, so they live in /tmp. Anonymous usage
# totals (D33) go to /data, where a private storage bucket is mounted so they
# survive restarts; without one they still work but reset on restart.
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf \
    FORKCAST_DEMO=1 \
    FORKCAST_DATA_DIR=/tmp/forkcast \
    FORKCAST_CORPUS_DB=/opt/forkcast/corpus.db \
    FORKCAST_STATS_DIR=/data/forkcast-stats \
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
ARG CORPUS_URL=https://github.com/rocky2397/forkcast-corpus/releases/download/corpus-20261114-d29/corpus.db
RUN mkdir -p /opt/forkcast \
 && curl -fsSL --retry 3 -o /opt/forkcast/corpus.db "$CORPUS_URL" \
 && python -c "\
import sqlite3,sys; \
n=sqlite3.connect('file:/opt/forkcast/corpus.db?mode=ro', uri=True).execute('SELECT COUNT(*) FROM recipes').fetchone()[0]; \
print(f'corpus ok: {n:,} recipes'); \
sys.exit(0 if n else 'corpus has no recipes')"

COPY --from=source /src/backend/ ./backend/
COPY --from=frontend /build/dist ./frontend/dist

# Everything is local from here on.
ENV HF_HUB_OFFLINE=1

EXPOSE 7860
# --no-proxy-headers: the request log shows Hugging Face's proxy, never a
# visitor's IP address (D33). The demo has no login to rate-limit per visitor.
CMD ["sh", "-c", "uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT} --no-proxy-headers"]
