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

# Run exactly what CI runs, in CI's order. CI invokes these same recipes step
# by step (see .github/workflows/python-ci.yml), so the two sets cannot drift:
# a check added here is added to CI, and a check CI needs must be added here.
ci: lint format-check check test cov-floor

# ── Testing ───────────────────────────────────────────────────────────────────

# The check suite: exactly the selection CI runs. Integration tests are excluded
# deliberately -- they need the tracker USB drive, which CI has no access to, so
# including them here would make the local result depend on what is plugged in.
test:
    uv run pytest -m "not slow and not integration" --cov-report=xml

# The drive-dependent tests, run deliberately when the tracker USB drive is
# mounted. Never part of `just ci` -- CI cannot run these at all.
test-integration:
    uv run pytest -m integration

# Same selection as `just test`, without coverage and stopping at the first
# failure. A development-loop convenience, not a check -- `just ci` is the check.
test-fast:
    uv run pytest -m "not slow and not integration" --no-cov -x

# Accept a deliberate change to the golden-master output. Rebuilds the files
# under tests/test_golden/golden/ from the synthetic tracker; read the diff
# before committing it. Unlike `snapshot-update` this needs no tracker drive --
# the workbook is built in code and nothing in it is real.
golden-update:
    uv run python scripts/update_golden.py

# Coverage floors, read from the data `just test` just wrote -- so run it after.
# Two floors, both 85%: the pipeline source as a whole (90% today), and the
# product modules specifically, which were the gap ticket 8 found. Measurement
# is confined to src/a4d by `--cov=src/a4d` in pyproject's addopts; the
# `--include` here is belt-and-braces so the floor cannot silently start
# grading test files if that ever changes.
cov-floor:
    uv run coverage report --include="src/a4d/*" --fail-under=85
    uv run coverage report \
        --include="src/a4d/extract/product.py,src/a4d/clean/product.py,src/a4d/clean/schema_product.py,src/a4d/extract/wide_format.py,src/a4d/pipeline/product.py,src/a4d/tables/product.py,src/a4d/validate/source_vs_output_product.py" \
        --fail-under=85

# ── Golden-master snapshot ───────────────────────────────────────

# Run both arms over the local tracker corpus and diff the output against the
# accepted baseline. Needs the tracker drive; never part of `just ci`, which
# has no corpus and must publish nothing about it. Cloud steps are all off --
# this reads and writes only the local drive.
#
# Run it before pushing anything that touches extraction, cleaning or tables.
# It fails whenever output moved, and says whether the code moved it (same
# workbook, different output) or the workbooks did (edited since the baseline).
snapshot-check:
    uv run a4d run --skip-download --skip-drive-download --skip-upload
    uv run a4d snapshot check

# Diff against the baseline without re-running the pipeline, reusing whatever
# output is already on the drive. The fast loop when you already know the run
# is current.
snapshot-diff:
    uv run a4d snapshot check

# Accept the last check's result as the new baseline. Runs nothing: there is
# nothing to accept until a check has shown you what moved. Record the
# acceptance in the commit message -- the digest itself stays on the drive.
snapshot-update:
    uv run a4d snapshot update

# Install the pre-push hook that runs `just ci` before every push
hooks:
    #!/usr/bin/env bash
    set -euo pipefail
    cp scripts/hooks/pre-push .git/hooks/pre-push
    chmod +x .git/hooks/pre-push
    echo "Installed .git/hooks/pre-push -> runs \`just ci\`"

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
# Named params (not *ARGS) so paths with spaces (e.g. the USB drive) survive just's interpolation
compare-outputs r_dir py_dir output_dir="output/comparison" *ARGS:
    uv run python scripts/compare_outputs.py \
        --r-dir "{{r_dir}}" --py-dir "{{py_dir}}" --output-dir "{{output_dir}}" {{ARGS}}

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

# Smoke test: verify the image starts and the CLI is reachable.
# --no-sync mirrors the Dockerfile CMD, so this exercises the startup path the
# Cloud Run Job actually takes. A bare `uv run` re-resolves from PyPI instead,
# which is what the deployed job must not do.
docker-smoke:
    docker run --rm {{IMAGE}} uv run --no-sync a4d --help

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
    # Derived from the pipeline itself, so a table added or renamed in the code
    # is snapshotted without anyone remembering to edit this recipe. The
    # hand-typed list this replaced had gone stale in both directions at once:
    # it still snapshotted the retired `errors` table and never covered
    # `findings`, which replaced it -- so the newest published table would have
    # been overwritten with no rollback point.
    TABLES=$(uv run python -c "from a4d.gcp.bigquery import published_table_names; print(' '.join(published_table_names()))")
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
