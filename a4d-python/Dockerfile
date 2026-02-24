FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /app

# Copy dependency files first to leverage Docker layer caching
COPY a4d-python/pyproject.toml a4d-python/uv.lock ./

# Install production dependencies only
RUN uv sync --frozen --no-dev

# Copy application code
COPY a4d-python/src/ src/

# Copy reference data from the repo root
COPY reference_data/ reference_data/

# Set environment
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV A4D_DATA_ROOT=/workspace/data

# Run the full pipeline: download → process → upload to GCS → ingest into BigQuery
CMD ["uv", "run", "a4d", "run-pipeline"]
