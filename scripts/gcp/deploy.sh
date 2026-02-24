#!/bin/bash
# Build the Docker image, push it to Artifact Registry, and deploy the A4D
# pipeline as a Cloud Run Job that can be triggered manually.
#
# Prerequisites:
#   - gcloud CLI authenticated with sufficient permissions
#   - Docker installed and running
#   - Service account "${SERVICE_ACCOUNT}" created with the following roles:
#       roles/storage.objectViewer       (read source files from GCS)
#       roles/storage.objectCreator      (write output files to GCS)
#       roles/bigquery.dataEditor        (write tables to BigQuery)
#       roles/bigquery.jobUser           (run BigQuery load jobs)
#       roles/secretmanager.secretAccessor (access the SA key secret)
#   - Secret "a4d-gcp-sa" created in Secret Manager containing the service
#     account JSON key used to authenticate googlesheets4/googledrive
#
# Usage:
#   PROJECT_ID=my-project SERVICE_ACCOUNT=sa@my-project.iam.gserviceaccount.com \
#     bash scripts/gcp/deploy.sh
#
# To run the pipeline after deployment:
#   gcloud run jobs execute a4d-pipeline \
#     --region=${REGION} --project=${PROJECT_ID} --wait

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-a4d-315220}"
REGION="${REGION:-europe-west1}"
REPOSITORY="a4d"
IMAGE_NAME="pipeline"
JOB_NAME="a4d-pipeline"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-a4d-pipeline@${PROJECT_ID}.iam.gserviceaccount.com}"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}"

echo "==> Configuring Docker authentication for Artifact Registry..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

echo "==> Creating Artifact Registry repository (skipped if it already exists)..."
gcloud artifacts repositories create "${REPOSITORY}" \
    --repository-format=docker \
    --location="${REGION}" \
    --project="${PROJECT_ID}" \
    --quiet 2>/dev/null || true

echo "==> Building Docker image: ${IMAGE_URI}"
docker build --cache-from "${IMAGE_URI}" -t "${IMAGE_URI}" .

echo "==> Pushing Docker image to Artifact Registry..."
docker push "${IMAGE_URI}"

echo "==> Deploying Cloud Run Job: ${JOB_NAME}"
gcloud run jobs deploy "${JOB_NAME}" \
    --image="${IMAGE_URI}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --service-account="${SERVICE_ACCOUNT}" \
    --memory=8Gi \
    --cpu=4 \
    --max-retries=0 \
    --task-timeout=3h \
    --set-secrets="/workspace/secrets/a4d-gcp-sa.json=a4d-gcp-sa:latest"

echo ""
echo "==> Deployment complete."
echo ""
echo "To run the pipeline manually, execute:"
echo "  gcloud run jobs execute ${JOB_NAME} \\"
echo "    --region=${REGION} --project=${PROJECT_ID} --wait"
