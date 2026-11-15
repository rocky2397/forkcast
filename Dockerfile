# Forkcast deployment image (D15).
#
# Everything that is identical across deploys is baked in here — frontend
# bundle, Epicure weights, recipe corpus — so a cold start does no network I/O
# and the persistent disk only ever holds the few KB of user data.

# ---- 1. Frontend bundle -----------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 2. Runtime -------------------------------------------------------------
FROM python:3.12-slim

# The recipe corpus (~130 MB, read-only). Render exposes service environment
# variables to the build as build args, so set FORKCAST_CORPUS_URL on the
# service. It must be *unauthenticated* — Render warns that build args can end
# up in image layers, so this is not the place for a token. See DEPLOY.md for
# publishing the corpus as a public GitHub Release asset.
ARG FORKCAST_CORPUS_URL=""

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf \
    FORKCAST_DATA_DIR=/var/data \
    FORKCAST_CORPUS_DB=/opt/forkcast/corpus.db

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Epicure weights at build time: embeddings.py would otherwise snapshot_download
# on the first request after every cold start (three repos, ~6 MB of vectors
# plus the loader module).
RUN python -c "\
from huggingface_hub import snapshot_download; \
[snapshot_download(m) for m in ('Kaikaku/epicure-cooc','Kaikaku/epicure-core','Kaikaku/epicure-chem')]"

RUN mkdir -p /opt/forkcast && \
    if [ -n "$FORKCAST_CORPUS_URL" ]; then \
        echo "Fetching recipe corpus..." && \
        curl -fsSL --retry 3 -o /opt/forkcast/corpus.db "$FORKCAST_CORPUS_URL" && \
        python -c "\
import sqlite3,sys; \
n=sqlite3.connect('/opt/forkcast/corpus.db').execute('SELECT COUNT(*) FROM recipes').fetchone()[0]; \
print(f'corpus ok: {n:,} recipes'); \
sys.exit(0 if n else 'corpus has no recipes')"; \
    else \
        echo "WARNING: FORKCAST_CORPUS_URL unset — image has no recipe corpus." >&2; \
    fi

COPY backend/ ./backend/
COPY --from=frontend /build/dist ./frontend/dist

# Mount point for the persistent disk holding forkcast.db. Created here so the
# image also runs without a disk attached (data is then ephemeral).
RUN mkdir -p /var/data
# Hosts like Hugging Face Spaces run the container as an unprivileged user: let
# it write the data dir and the model cache's lock files.
RUN chmod -R a+rwX /var/data /opt/hf

# Render supplies $PORT; default matches the local dev port.
ENV PORT=8000

# --proxy-headers makes request.client the real caller rather than Render's
# load balancer, so the login rate limiter buckets per client instead of
# lumping everyone together. Trusting any peer's X-Forwarded-For is safe here
# because only the platform proxy can reach the container.
CMD ["sh", "-c", "uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
