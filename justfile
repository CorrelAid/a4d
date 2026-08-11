# a4d Python Pipeline - Development Commands

# Default recipe (show available commands)
default:
    @just --list

PROJECT  := "a4dphase2"
DATASET  := "tracker"
REGISTRY := "asia-southeast2-docker.pkg.dev/a4dphase2/a4d/pipeline"
IMAGE    := REGISTRY + ":latest"

# ── Environment ───────────────────────────────────────────────────────────────

# Install dependencies and sync environment
sync:
    uv sync --all-extras

# Update dependencies
update:
    uv lock --upgrade

# Show project info
info:
    @echo "Python version:"
    @uv run python --version
    @echo ""
    @echo "Installed packages:"
    @uv pip list

# Clean cache and build artifacts
clean:
    rm -rf .ruff_cache .pytest_cache htmlcov .coverage dist build src/*.egg-info
    find . -type d -name __pycache__ -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete

# ── Code Quality ──────────────────────────────────────────────────────────────

# Format code with ruff
format:
    uv run ruff format .

# Check code formatting without modifying files
format-check:
    uv run ruff format --check .

# Auto-fix linting issues
fix:
    uv run ruff check --fix .

# Run ruff linting
lint:
    uv run ruff check .

# Run type checking with ty
check:
    uv run ty check src/

# Run all CI checks (format, lint, type, test)
ci: format-check lint check test

# ── Testing ───────────────────────────────────────────────────────────────────

# Run unit tests (skip slow/integration)
test:
    uv run pytest -m "not slow"

# Run tests without coverage (faster, fail fast)
test-fast:
    uv run pytest -m "not slow" --no-cov -x

# Run all tests including slow/integration
test-all:
    uv run pytest

# Run integration tests only
test-integration:
    uv run pytest -m integration

# Install pre-commit hooks
hooks:
    uv run pre-commit install

# Run pre-commit on all files
hooks-run:
    uv run pre-commit run --all-files

# ── Local Pipeline ────────────────────────────────────────────────────────────

# Process a single patient tracker file (no GCS)
run-file FILE:
    uv run a4d run patient --file "{{FILE}}"

# Process a single product tracker file (no GCS); ad-hoc/debug only — use `just run` for full runs
run-file-product FILE:
    uv run a4d run product --file "{{FILE}}"

# Process local patient files only, no GCS (paths with spaces: use --file recipes instead)
run-local *ARGS:
    uv run a4d run patient {{ARGS}}

# Process local product files only, no GCS; ad-hoc/debug only — use `just run` for full runs
run-local-product *ARGS:
    uv run a4d run product {{ARGS}}

# Rebuild patient+product+clinic+logs tables from existing cleaned output
create-tables *ARGS:
    uv run a4d create tables {{ARGS}}

# Download from GCS, process locally, no upload
run-download *ARGS:
    uv run a4d run --skip-upload {{ARGS}}

# Full pipeline: download from GCS, process, upload to GCS + BigQuery
run *ARGS:
    uv run a4d run {{ARGS}}

# Diff a Python output directory against the frozen R baseline (migration-only, ticket 15)
compare-outputs *ARGS:
    uv run python scripts/compare_outputs.py {{ARGS}}

# ── Docker ────────────────────────────────────────────────────────────────────

# --provenance=false: suppress BuildKit attestation manifests so the registry
# shows one image entry instead of three (image + attestation + index)
# Build Docker image tagged as :latest and :<git-sha>
docker-build:
    #!/usr/bin/env bash
    set -euo pipefail
    GIT_SHA=$(git rev-parse --short HEAD)
    docker build --provenance=false --platform=linux/amd64 \
        -t {{IMAGE}} \
        -t {{REGISTRY}}:${GIT_SHA} \
        -f Dockerfile .

# Smoke test: verify the image starts and the CLI is reachable
docker-smoke:
    docker run --rm {{IMAGE}} uv run a4d --help

# Push both :latest and :<git-sha> tags to Artifact Registry
docker-push: docker-build
    #!/usr/bin/env bash
    set -euo pipefail
    GIT_SHA=$(git rev-parse --short HEAD)
    docker push {{IMAGE}}
    docker push {{REGISTRY}}:${GIT_SHA}
    echo "Pushed: {{IMAGE}} and {{REGISTRY}}:${GIT_SHA}"

# Delete all images from Artifact Registry except :latest
docker-clean:
    #!/usr/bin/env bash
    set -euo pipefail
    LATEST=$(gcloud artifacts docker images describe {{IMAGE}} \
        --project={{PROJECT}} --format="value(image_summary.digest)")
    echo "Keeping: {{IMAGE}} ($LATEST)"
    gcloud artifacts docker images list {{REGISTRY}} \
        --include-tags --project={{PROJECT}} \
        --format="value(digest)" \
    | while read -r digest; do
        if [ "$digest" != "$LATEST" ]; then
            echo "Deleting $digest..."
            gcloud artifacts docker images delete "{{REGISTRY}}@$digest" \
                --project={{PROJECT}} --quiet --delete-tags 2>/dev/null || true
        fi
    done
    echo "Done."

# List images in Artifact Registry with tags and digests
docker-list:
    gcloud artifacts docker images list {{REGISTRY}} \
        --include-tags \
        --project={{PROJECT}}

# ── GCP / Cloud Run ───────────────────────────────────────────────────────────

# Creates dated snapshots e.g. patient_data_static_20260227 with 7-day expiry.
# Snapshot all BigQuery pipeline tables (safe to run before deploy)
backup-bq:
    #!/usr/bin/env bash
    set -euo pipefail
    DATE=$(date +%Y%m%d)
    EXPIRY="TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)"
    # Output data tables that get WRITE_TRUNCATE'd by load_pipeline_tables on every run.
    # Keep in sync with PARQUET_TO_TABLE in src/a4d/gcp/bigquery.py when adding new pipelines.
    TABLES="patient_data_static patient_data_monthly patient_data_annual product_data"
    for TABLE in $TABLES; do
        if bq show --quiet {{PROJECT}}:{{DATASET}}.${TABLE} 2>/dev/null; then
            SNAP="${TABLE}_${DATE}"
            echo "Snapshotting ${TABLE} -> ${SNAP}..."
            bq query --use_legacy_sql=false --project_id={{PROJECT}} \
                "CREATE SNAPSHOT TABLE \`{{PROJECT}}.{{DATASET}}.${SNAP}\`
                 CLONE \`{{PROJECT}}.{{DATASET}}.${TABLE}\`
                 OPTIONS(expiration_timestamp = ${EXPIRY})"
        else
            echo "Skipping ${TABLE} (does not exist yet)"
        fi
    done
    echo "Done. Snapshots expire in 7 days."

# Build, push and update the Cloud Run Job to use the latest image
deploy: docker-push
    gcloud run jobs update a4d-pipeline \
        --image={{IMAGE}} \
        --region=asia-southeast2

# Execute the Cloud Run Job
run-job:
    gcloud run jobs execute a4d-pipeline --region=asia-southeast2

# Stream logs from the Cloud Run Job (Ctrl-C to stop)
logs-job:
    gcloud beta logging tail 'resource.type="cloud_run_job" AND resource.labels.job_name="a4d-pipeline"' \
        --project={{PROJECT}} \
        --format="value(textPayload)"

# Show current resource settings (CPU, memory, timeout, parallelism) for the Cloud Run Job
job-settings:
    gcloud run jobs describe a4d-pipeline \
        --region=asia-southeast2 \
        --project={{PROJECT}} \
        --format="yaml(spec.template.spec.template.spec.containers[0].resources, spec.template.spec.template.spec.timeoutSeconds, spec.template.spec.parallelism, spec.template.spec.taskCount)"

# Roll back Cloud Run Job to a specific git SHA
# Usage: just rollback abc1234
rollback SHA:
    gcloud run jobs update a4d-pipeline \
        --image={{REGISTRY}}:{{SHA}} \
        --region=asia-southeast2
    @echo "Rolled back to {{REGISTRY}}:{{SHA}}"
