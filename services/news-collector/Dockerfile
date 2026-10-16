# Build context = repo root:  docker build -f services/news-collector/Dockerfile .
# base ghim digest (Renovate cập nhật); lock có hash: services/news-collector/requirements.lock (infra/ops/lock_deps.sh)
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY services/news-collector/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock
COPY libs/common /app/libs/common
COPY services/news-collector /app/services/news-collector
RUN pip install --no-deps /app/libs/common /app/services/news-collector
ENV NC_CONFIG_DIR=/app/services/news-collector/config SERVICE_NAME=news-collector PORT=8000
EXPOSE 8000
CMD ["python", "-m", "news_collector.main"]
