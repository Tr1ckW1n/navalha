# Imagem única: o FastAPI serve a API (/api) e o site React (todo o resto) na mesma URL.
# Build: gcloud run deploy --source .   (ver deploy/GUIA.md)

FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 ENV=prod REPOSITORY=firestore STATIC_DIR=static
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/data ./data
COPY --from=web /web/dist ./static
RUN useradd --create-home app && chown -R app /app
USER app
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
