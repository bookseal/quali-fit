FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY Data/ ./Data/

RUN useradd -m -u 10001 app \
 && mkdir -p /data \
 && chown -R app:app /data /app
USER app

# Build/version stamp — injected at build time (deploy.sh passes these), surfaced
# in the app's sidebar footer so you can confirm which build is actually live.
# Kept late in the file so the per-build values don't bust the pip-install cache.
ARG APP_VERSION=dev
ARG GIT_SHA=local
ARG BUILD_TIME=unknown
ENV APP_VERSION=$APP_VERSION \
    GIT_SHA=$GIT_SHA \
    BUILD_TIME=$BUILD_TIME

EXPOSE 8501

# init_db is idempotent (CREATE TABLE IF NOT EXISTS). The real DB is supplied
# via `kubectl cp` into the PVC, so we do NOT auto-seed here.
CMD ["sh", "-c", "python -c 'import db; db.init_db()' && exec streamlit run app.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true --browser.gatherUsageStats=false"]
