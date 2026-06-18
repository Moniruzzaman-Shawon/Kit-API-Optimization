# Live demo of the Kit toolkit.
# Runs the FastAPI example app (example-app/main.py) on fakeredis — no external
# Redis required — so it deploys anywhere with zero configuration.
#
# Build context must be the repo root (the image installs the four sibling packages).
FROM python:3.12-slim

WORKDIR /app

# Install the four Kit packages from source. Passing them in one command lets pip
# satisfy the inter-package `kit-core` dependency locally (nothing is fetched from PyPI).
COPY kit-core kit-core
COPY kit-api kit-api
COPY kit-media kit-media
COPY kit-pay kit-pay
RUN pip install --no-cache-dir ./kit-core ./kit-api ./kit-media ./kit-pay

# Demo-only runtime deps (FastAPI, uvicorn, fakeredis, …).
COPY example-app example-app
RUN pip install --no-cache-dir -r example-app/requirements.txt

WORKDIR /app/example-app
ENV PORT=8000
# Hosts (Render/Fly/Railway) inject $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
