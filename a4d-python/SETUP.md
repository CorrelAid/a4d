# A4D Pipeline — Setup Guide

## Local Development

### Prerequisites

```bash
# uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# just (command runner)
brew install just

# gcloud CLI
brew install google-cloud-sdk
```

### Install

```bash
cd a4d-python
uv sync
cp .env.example .env
```

> `.env` is only used for local development. On GCP, environment variables are
> set directly on the Cloud Run Job (see step 5 in the GCP section below) and
> the `.env` file is not present or needed in the container.

Edit `.env` — only these fields matter locally:

```bash
A4D_DATA_ROOT=/path/to/tracker/files   # folder containing .xlsx trackers
A4D_PROJECT_ID=a4dphase2
A4D_DATASET=tracker
A4D_DOWNLOAD_BUCKET=a4dphase2_upload
A4D_UPLOAD_BUCKET=a4dphase2_output
```

**Paths with spaces** (e.g. a USB drive): write the value unquoted in `.env` —
pydantic-settings reads to end of line and handles spaces correctly:

```bash
A4D_DATA_ROOT=/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload
```

### Authenticate

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project a4dphase2
```

### Run

```bash
# Test with a single file (fastest)
just run-file /path/to/tracker.xlsx

# Process all files already in A4D_DATA_ROOT — no GCS
just run-local

# Download latest files from GCS, process locally — no upload
just run-download

# Full pipeline: download from GCS, process, upload results + load BigQuery
just run
```

For paths with spaces, wrap the argument in quotes:

```bash
just run-file "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/2024_Penang.xlsx"
```

---

## Google Cloud Deployment

The pipeline runs as a **Cloud Run Job** — a one-shot container that downloads
tracker files from GCS, processes them, and loads the results into BigQuery.
A service account is used instead of personal credentials.

> **Data residency**: All GCP resources (Artifact Registry, Cloud Run Job,
> Cloud Scheduler, BigQuery dataset, GCS buckets) must be located in
> **`asia-southeast2` (Jakarta)**. Patient data must not be processed or stored
> in the EU.

> **Steps 1–4 are one-time infrastructure setup.** Once the service account,
> IAM roles, and Artifact Registry repository exist, you only need to rebuild
> and redeploy (steps 4–5) when the code changes.

### 1. Create the service account

This only needs to be done once. Check if it already exists first:

```bash
gcloud iam service-accounts describe \
    a4d-pipeline@a4dphase2.iam.gserviceaccount.com \
    --project=a4dphase2
```

If it doesn't exist yet, create it:

```bash
gcloud iam service-accounts create a4d-pipeline \
    --display-name="A4D Pipeline Runner" \
    --project=a4dphase2
```

### 2. Grant IAM roles

The service account needs access to two GCS buckets and the BigQuery dataset.

> Both GCS buckets (`a4dphase2_upload`, `a4dphase2_output`) must be located in
> `asia-southeast2`. Bucket location is set at creation time and cannot be
> changed.

**GCS — read tracker files:**

```bash
gcloud storage buckets add-iam-policy-binding gs://a4dphase2_upload \
    --member="serviceAccount:a4d-pipeline@a4dphase2.iam.gserviceaccount.com" \
    --role="roles/storage.objectViewer"
```

**GCS — write pipeline output:**

```bash
gcloud storage buckets add-iam-policy-binding gs://a4dphase2_output \
    --member="serviceAccount:a4d-pipeline@a4dphase2.iam.gserviceaccount.com" \
    --role="roles/storage.objectCreator"
```

> `objectCreator` grants only `storage.objects.create` — sufficient for upload.
> `objectAdmin` (broader) is not needed as the pipeline never reads, lists, or
> manages IAM on the output bucket.

> The BigQuery dataset `tracker` must be created in `asia-southeast2`. Dataset
> location is set at creation time and cannot be changed. If the dataset already
> exists in another region, it must be deleted and recreated (data loss — export
> first).

**BigQuery — run jobs (project-level):**

```bash
gcloud projects add-iam-policy-binding a4dphase2 \
    --member="serviceAccount:a4d-pipeline@a4dphase2.iam.gserviceaccount.com" \
    --role="roles/bigquery.jobUser"
```

**BigQuery — read/write tables in the `tracker` dataset:**

```bash
bq add-iam-policy-binding \
    --member="serviceAccount:a4d-pipeline@a4dphase2.iam.gserviceaccount.com" \
    --role="roles/bigquery.dataEditor" \
    a4dphase2:tracker
```

> `dataEditor` is scoped to the `tracker` dataset only, not the whole project.
> It is the most granular predefined role that allows creating and overwriting
> tables (WRITE_TRUNCATE load jobs require `tables.create` + `tables.updateData`).

### 3. Set up Artifact Registry

```bash
# Create the repository (once)
gcloud artifacts repositories create a4d \
    --repository-format=docker \
    --location=asia-southeast2 \
    --project=a4dphase2

# Allow the service account to pull images
gcloud artifacts repositories add-iam-policy-binding a4d \
    --location=asia-southeast2 \
    --member="serviceAccount:a4d-pipeline@a4dphase2.iam.gserviceaccount.com" \
    --role="roles/artifactregistry.reader" \
    --project=a4dphase2
```

### 4. Build and push the Docker image

Authenticate Docker to Artifact Registry once:

```bash
gcloud auth configure-docker asia-southeast2-docker.pkg.dev
```

Then build and push (run from `a4d-python/`):

```bash
just docker-push
```

This builds with the repo root as context (required — the Dockerfile copies
`reference_data/` from outside `a4d-python/`) and pushes to Artifact Registry.

To verify the image was pushed and see what's already in the registry:

```bash
gcloud artifacts docker images list \
    asia-southeast2-docker.pkg.dev/a4dphase2/a4d \
    --include-tags \
    --project=a4dphase2
```

### 5. Create the Cloud Run Job

```bash
gcloud run jobs create a4d-pipeline \
    --image=asia-southeast2-docker.pkg.dev/a4dphase2/a4d/pipeline:latest \
    --region=asia-southeast2 \
    --service-account=a4d-pipeline@a4dphase2.iam.gserviceaccount.com \
    --set-env-vars="\
A4D_PROJECT_ID=a4dphase2,\
A4D_DATASET=tracker,\
A4D_DOWNLOAD_BUCKET=a4dphase2_upload,\
A4D_UPLOAD_BUCKET=a4dphase2_output,\
A4D_DATA_ROOT=/tmp/data,\
A4D_OUTPUT_DIR=output" \
    --memory=8Gi \
    --cpu=8 \
    --task-timeout=3600 \
    --project=a4dphase2
```

`A4D_DATA_ROOT=/tmp/data` uses ephemeral in-container storage — the job downloads
tracker files there, processes them, uploads the output, then exits. Nothing persists.

To update the job after a config change:

```bash
gcloud run jobs update a4d-pipeline --region=asia-southeast2 [--set-env-vars=...]
```

To list all existing jobs:

```bash
gcloud run jobs list --region=asia-southeast2 --project=a4dphase2
```

### 5a. Test the image locally before deploying

Always verify a newly built image works before creating or updating the Cloud Run Job.

**Level 1 — smoke test** (image starts, CLI is reachable):

```bash
just docker-smoke
# or:
docker run --rm asia-southeast2-docker.pkg.dev/a4dphase2/a4d/pipeline:latest \
    uv run a4d --help
```

**Level 2 — local pipeline run** (no GCS, process a local file):

Mount a directory containing tracker files and run `process-patient`. Output lands in
`/data/output` inside the container, which is the same mount so you can inspect it
afterward.

```bash
docker run --rm \
    -v /path/to/trackers:/data \
    -e A4D_DATA_ROOT=/data \
    asia-southeast2-docker.pkg.dev/a4dphase2/a4d/pipeline:latest \
    uv run a4d process-patient --file /data/your_tracker.xlsx
```

**Level 3 — full pipeline with GCP** (real GCS + BigQuery, no download):

Mount your local Application Default Credentials so the container can authenticate.
Use `--skip-download` to process files already on disk instead of fetching from GCS.

```bash
docker run --rm \
    -v /path/to/trackers:/data \
    -v "$HOME/.config/gcloud:/root/.config/gcloud:ro" \
    -e A4D_DATA_ROOT=/data \
    -e GOOGLE_CLOUD_PROJECT=a4dphase2 \
    asia-southeast2-docker.pkg.dev/a4dphase2/a4d/pipeline:latest \
    uv run a4d run-pipeline --skip-download
```

This exercises the full upload path (GCS + BigQuery) without touching the live tracker
source bucket.

### 6. Execute

```bash
just run-job    # trigger the Cloud Run Job
just logs-job   # stream logs from the latest execution
```

After a code change, redeploy and run in one step:

```bash
just deploy && just run-job
```

### 7. Schedule (optional)

To run the pipeline on a schedule, create a Cloud Scheduler job that triggers it:

```bash
gcloud scheduler jobs create http a4d-pipeline-weekly \
    --schedule="0 6 * * 1" \
    --uri="https://asia-southeast2-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/a4dphase2/jobs/a4d-pipeline:run" \
    --http-method=POST \
    --oauth-service-account-email=a4d-pipeline@a4dphase2.iam.gserviceaccount.com \
    --location=asia-southeast2
```

The service account also needs permission to trigger Cloud Run Jobs for this:

```bash
gcloud projects add-iam-policy-binding a4dphase2 \
    --member="serviceAccount:a4d-pipeline@a4dphase2.iam.gserviceaccount.com" \
    --role="roles/run.invoker"
```
