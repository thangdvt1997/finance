# Build từ gốc repo: docker build -f services/api-gateway/Dockerfile .
# base ghim digest (Renovate cập nhật); lock có hash: services/api-gateway/requirements.lock (infra/ops/lock_deps.sh)
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
WORKDIR /app
COPY services/api-gateway/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock
COPY libs/common /app/libs/common
COPY services/api-gateway /app/services/api-gateway
RUN pip install --no-cache-dir --no-deps /app/libs/common /app/services/api-gateway && useradd -r -u 10001 app
ENV PORT=8000
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:'+os.getenv('PORT','8000')+'/healthz')"
CMD ["python", "-m", "api_gateway.main"]
