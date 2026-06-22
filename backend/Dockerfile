FROM python:3.11

# uv for fast, lockfile-pinned installs
COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /uvx /bin/

WORKDIR /app

# Install deps first so this layer caches when only source changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# App source (data dirs are excluded via .dockerignore — they live on a volume)
COPY . .

# Persisted data lives on a mounted Railway volume in prod
ENV DATA_ROOT=/data
EXPOSE 5001

# Single process: embedded LadybugDB allows only one lock holder, so never run
# multiple workers/replicas. run.py binds $PORT (Railway) or FLASK_PORT.
CMD ["uv", "run", "python", "run.py"]
