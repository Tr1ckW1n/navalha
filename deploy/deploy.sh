#!/usr/bin/env bash
# Sobe o Navalha no Google Cloud (Cloud Run + Firestore). Rodar no Cloud Shell, na pasta navalha/.
#   PROJECT_ID=seu-projeto bash deploy/deploy.sh
# Pode rodar de novo quando quiser: só cria o que falta e atualiza o resto.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Defina PROJECT_ID, ex.: PROJECT_ID=navalha-mf bash deploy/deploy.sh}"
REGION="${REGION:-southamerica-east1}"   # São Paulo
SERVICE="${SERVICE:-navalha}"
SECRET="navalha-admin-key"
DATA_FILE="${DATA_FILE:-backend/data/barbearia-mf.json}"

step() { printf '\n\033[1;31m==>\033[0m %s\n' "$*"; }

[ -f Dockerfile ] || { echo "Rode na pasta navalha/ (onde está o Dockerfile)."; exit 1; }

step "Projeto $PROJECT_ID"
gcloud config set project "$PROJECT_ID" >/dev/null
BILLING=$(gcloud beta billing projects describe "$PROJECT_ID" --format='value(billingEnabled)' 2>/dev/null || echo "")
if [ "$BILLING" != "True" ]; then
  echo "O projeto precisa de uma conta de faturamento vinculada (Cloud Run e Cloud Build exigem; o uso fica na cota grátis)."
  echo "Vincule em: https://console.cloud.google.com/billing/linkedaccount?project=$PROJECT_ID  e rode de novo."
  exit 1
fi

step "Ativando APIs (leva 1–2 min na primeira vez)"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com secretmanager.googleapis.com

step "Firestore (modo nativo, $REGION)"
if gcloud firestore databases describe --database="(default)" >/dev/null 2>&1; then
  echo "já existe"
else
  gcloud firestore databases create --location="$REGION" --type=firestore-native
fi

step "Índices do Firestore (criação continua em segundo plano)"
idx() { gcloud firestore indexes composite create --collection-group="$1" "${@:2}" --async >/dev/null 2>&1 && echo "criado: $1" || echo "ok (já existe): $1"; }
idx appointments --field-config=field-path=barbershopId,order=ascending --field-config=field-path=barberId,order=ascending --field-config=field-path=startsAt,order=ascending
idx appointments --field-config=field-path=barbershopId,order=ascending --field-config=field-path=startsAt,order=ascending
idx blocks --field-config=field-path=barbershopId,order=ascending --field-config=field-path=barberId,order=ascending --field-config=field-path=start,order=ascending

step "Chave do painel (Secret Manager)"
if gcloud secrets describe "$SECRET" >/dev/null 2>&1; then
  echo "já existe. Para ver: gcloud secrets versions access latest --secret=$SECRET"
else
  KEY=$(openssl rand -hex 12)
  printf %s "$KEY" | gcloud secrets create "$SECRET" --data-file=- --replication-policy=automatic >/dev/null
  echo "CHAVE DO PAINEL (guarde): $KEY"
fi

step "Permissões da conta de serviço do Cloud Run"
PN=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
SA="${PN}-compute@developer.gserviceaccount.com"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA" --role=roles/datastore.user --condition=None -q >/dev/null
gcloud secrets add-iam-policy-binding "$SECRET" --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor -q >/dev/null
echo "ok: $SA"

step "Build e deploy no Cloud Run (3–6 min)"
gcloud run deploy "$SERVICE" --source . --region "$REGION" --allow-unauthenticated \
  --max-instances 2 --memory 512Mi --cpu 1 \
  --set-env-vars "ENV=prod,GCP_PROJECT_ID=$PROJECT_ID,REPOSITORY=firestore" \
  --set-secrets "ADMIN_API_KEY=$SECRET:latest"

step "Dados da barbearia ($DATA_FILE)"
python3 -m venv /tmp/navalha-venv >/dev/null && . /tmp/navalha-venv/bin/activate
pip install -q -r backend/requirements.txt
(cd backend && GCP_PROJECT_ID="$PROJECT_ID" python -m scripts.seed --real --project "$PROJECT_ID" --file "${DATA_FILE#backend/}")

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
SLUG=$(python3 -c "import json;print(json.load(open('$DATA_FILE'))['shop']['slug'])")
step "Pronto"
echo "Link para os clientes:  $URL/$SLUG"
echo "Painel do dono:         $URL/$SLUG/painel   (chave: gcloud secrets versions access latest --secret=$SECRET)"
echo "Saúde da API:           $URL/health"
