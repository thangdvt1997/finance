# Build từ gốc repo: docker build -f services/analytics/Dockerfile .
# Base ghim digest (Renovate); lock có hash: services/analytics/requirements.lock (infra/ops/lock_deps.sh analytics), chỉ nhận wheel.
# TA-Lib >= 0.6 có wheel manylinux (đã đóng gói sẵn thư viện C) nên KHÔNG cần trình biên dịch/gcc.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
WORKDIR /app
COPY services/analytics/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes -r /app/requirements.lock
COPY libs/common /app/libs/common
COPY services/analytics /app/services/analytics
RUN pip install --no-cache-dir --no-deps /app/libs/common /app/services/analytics \
 && useradd -r -u 10001 app
ENV PORT=8000 ANALYTICS_CONFIG=/app/services/analytics/analytics.example.yaml
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:'+os.getenv('PORT','8000')+'/healthz')"
CMD ["python", "-m", "analytics.main"]
