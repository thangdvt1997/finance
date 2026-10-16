# Build tu thu muc goc repo:  docker build -f services/mt-bridge/Dockerfile -t mt-bridge .
# Image Linux: CHI HTTP ingest (EA MT4/MT5) + publish. Adapter MT5 truc tiep (package MetaTrader5)
# chi chay duoc tren Windows -> KHONG co trong image nay (accounts transport=mt5_direct se bao loi khi connect).
# base ghim digest (Renovate cập nhật); lock có hash: services/mt-bridge/requirements.lock (infra/ops/lock_deps.sh)
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 SERVICE_NAME=mt-bridge PORT=8000
WORKDIR /app
COPY services/mt-bridge/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock
COPY libs/common /app/libs/common
COPY services/mt-bridge /app/services/mt-bridge
RUN pip install --no-deps /app/libs/common /app/services/mt-bridge
RUN useradd -r -u 10001 bridge && mkdir -p /config && chown bridge /config
USER bridge
ENV BRIDGE_CONFIG=/config/accounts.yaml
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:%s/healthz'%os.getenv('PORT','8000'))"
CMD ["sh", "-c", "uvicorn mtbridge.service:create_default_app --factory --host 0.0.0.0 --port ${PORT}"]