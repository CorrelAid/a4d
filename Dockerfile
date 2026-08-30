FROM python:3.14-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install uv from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Use the system Python from the base image; do not let uv download its own
ENV UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install dependencies first (without the project) for better layer caching.
# --no-install-project skips the editable install of a4d itself, which requires
# src/ to be present. Dependencies rarely change so this layer stays cached.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code and reference data
COPY src/ src/
COPY reference_data/ reference_data/

# Install the project itself now that src/ exists
RUN uv sync --frozen --no-dev

# Set environment
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV A4D_DATA_ROOT=/workspace/data
ENV A4D_REFERENCE_DATA=/app/reference_data

# --no-sync runs the venv the image already built. Without it `uv run`
# re-resolves at container start: the smoke test showed it pulling ruff and ty
# from PyPI on every cold start -- dev tooling the job never uses -- which
# makes startup depend on network reachability and means the running set is
# not necessarily the one `uv sync --frozen` locked at build time.
# Run the full pipeline: download → process → upload to GCS → ingest into BigQuery
CMD ["uv", "run", "--no-sync", "a4d", "run"]
