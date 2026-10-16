# Build từ gốc repo: docker build -f services/risk-monitor/Dockerfile .
# Base ghim digest; lock có hash: services/risk-monitor/requirements.lock (infra/ops/lock_deps.sh risk-monitor), chỉ nhận wheel (numpy/pandas) nên không cần trình biên dịch.
# Service CHỈ ĐỌC DB (ts_ro) + phát cảnh báo lên Redis.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
WORKDIR /app
COPY services/risk-monitor/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes -r /app/requirements.lock
COPY libs/common /app/libs/common
COPY services/risk-monitor /app/services/risk-monitor
RUN pip install --no-cache-dir --no-deps /app/libs/common /app/services/risk-monitor \
 && useradd -r -u 10001 app
ENV PORT=8000 RISK_CONFIG=/app/services/risk-monitor/risk.example.yaml
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:'+os.getenv('PORT','8000')+'/healthz')"
CMD ["python", "-m", "risk_monitor.main"]
