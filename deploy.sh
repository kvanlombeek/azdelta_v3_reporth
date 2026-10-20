#!/usr/bin/env bash
# Bouwt en deployt Reporth v3 naar Cloud Run. Idempotent: maakt enkel aan wat nog ontbreekt.
# Bevat geen secrets; die komen uit Secret Manager (zie README).
set -euo pipefail

PROJECT_ID=orthopediereportingproject
REGION=europe-west1
SERVICE=reporth-v3
REPO=reporth            # Artifact Registry repo

# Eigen serviceaccounts per service, zoals bij procedure-finder.
RUN_SA="${SERVICE}@${PROJECT_ID}.iam.gserviceaccount.com"
BUILD_SA="${SERVICE}-build@${PROJECT_ID}.iam.gserviceaccount.com"

SECRET_CLIENT=reporth-v3-entra-client-secret
SECRET_SESSION=reporth-v3-session-secret
SECRET_DB=reporth-v3-database-url

# Cloud SQL: op Cloud Run geen Auth Proxy nodig. --add-cloudsql-instances maakt de socket
# /cloudsql/<instance> aan; DATABASE_URL (in Secret Manager) wijst daarnaar.
SQL_INSTANCE=orthopediereportingproject:europe-west1:orthopedie-reporting-db

BASE_URL=https://v3.reporth.be
ENTRA_CLIENT_ID=d9a501a1-7c73-4c19-98dc-2a9b6d35f3c3
ENTRA_AUTHORITY=de5dcc4b-b4d4-4eca-8851-2cb8bdd62c7b  # Reporth-tenant (gasten); terug naar "organizations" na admin consent van ziekenhuizen
ENTRA_ALLOWED_TENANTS=de5dcc4b-b4d4-4eca-8851-2cb8bdd62c7b,0d2411fc-02b6-455e-86db-122a475d9273
ENTRA_ALLOWED_EMAILS=

IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${SERVICE}:$(date +%Y%m%d-%H%M%S)"

echo "==> Project ${PROJECT_ID}"
gcloud config set project "${PROJECT_ID}"

echo "==> Secrets controleren"
for s in "${SECRET_CLIENT}" "${SECRET_SESSION}" "${SECRET_DB}"; do
  if ! gcloud secrets describe "${s}" >/dev/null 2>&1; then
    echo "Secret '${s}' bestaat niet. Maak het eerst aan (zie README)." >&2
    exit 1
  fi
done

echo "==> Artifact Registry-repo ${REPO}"
gcloud artifacts repositories describe "${REPO}" --location "${REGION}" >/dev/null 2>&1 \
  || gcloud artifacts repositories create "${REPO}" --repository-format docker --location "${REGION}" \
       --description "Reporth v3 images"

echo "==> Serviceaccounts"
gcloud iam service-accounts describe "${RUN_SA}" >/dev/null 2>&1 \
  || gcloud iam service-accounts create "${SERVICE}" --display-name "Reporth v3 (Cloud Run)"
gcloud iam service-accounts describe "${BUILD_SA}" >/dev/null 2>&1 \
  || gcloud iam service-accounts create "${SERVICE}-build" --display-name "Reporth v3 (Cloud Build)"

# Een nieuwe serviceaccount is pas na enkele seconden zichtbaar voor IAM: probeer opnieuw.
retry() {
  for i in 1 2 3 4 5 6; do
    "$@" >/dev/null 2>&1 && return 0
    echo "    nog niet gelukt, opnieuw over 10 s (${i}/6)"
    sleep 10
  done
  "$@" >/dev/null  # laatste poging, toont de fout
}

echo "==> IAM-rechten (idempotent)"
retry gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member "serviceAccount:${BUILD_SA}" --role roles/run.builder --condition None
retry gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member "serviceAccount:${RUN_SA}" --role roles/cloudsql.client --condition None
for s in "${SECRET_CLIENT}" "${SECRET_SESSION}" "${SECRET_DB}"; do
  retry gcloud secrets add-iam-policy-binding "${s}" \
    --member "serviceAccount:${RUN_SA}" --role roles/secretmanager.secretAccessor
done

echo "==> Image bouwen: ${IMAGE}"
gcloud builds submit . \
  --region "${REGION}" \
  --config cloudbuild.yaml \
  --substitutions "_IMAGE=${IMAGE}" \
  --service-account "projects/${PROJECT_ID}/serviceAccounts/${BUILD_SA}" \
  --default-buckets-behavior REGIONAL_USER_OWNED_BUCKET

echo "==> Deployen naar Cloud Run"
# '^;^' zet het scheidingsteken op ';', want ENTRA_ALLOWED_TENANTS bevat komma's.
gcloud run deploy "${SERVICE}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "${RUN_SA}" \
  --add-cloudsql-instances "${SQL_INSTANCE}" \
  --allow-unauthenticated \
  --memory 512Mi \
  --min-instances 0 \
  --max-instances 2 \
  --set-env-vars "^;^ENTRA_CLIENT_ID=${ENTRA_CLIENT_ID};ENTRA_AUTHORITY=${ENTRA_AUTHORITY};ENTRA_REDIRECT_URI=${BASE_URL}/auth/callback;ENTRA_POST_LOGOUT_URI=${BASE_URL}/auth/logged-out;ENTRA_ALLOWED_TENANTS=${ENTRA_ALLOWED_TENANTS};ENTRA_ALLOWED_EMAILS=${ENTRA_ALLOWED_EMAILS};SESSION_HTTPS_ONLY=true" \
  --set-secrets "ENTRA_CLIENT_SECRET=${SECRET_CLIENT}:latest,SESSION_SECRET=${SECRET_SESSION}:latest,DATABASE_URL=${SECRET_DB}:latest"

echo "==> Service-URL"
gcloud run services describe "${SERVICE}" --region "${REGION}" --format 'value(status.url)'
echo "Custom domein: ${BASE_URL} (zie README voor de domain mapping)"
