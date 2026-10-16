# Build từ gốc repo: docker build -f services/pattern-engine/Dockerfile .
# Base ghim digest (Renovate) giống analytics; lock có hash: services/pattern-engine/requirements.lock (infra/ops/lock_deps.sh pattern-engine), chỉ nhận wheel.
# Thuần Python (không TA-Lib/numpy): ATR/ZigZag tự cài, tất định, không cần gcc.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
WORKDIR /app
COPY services/pattern-engine/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes -r /app/requirements.lock
COPY libs/common /app/libs/common
COPY services/pattern-engine /app/services/pattern-engine
RUN pip install --no-cache-dir --no-deps /app/libs/common /app/services/pattern-engine \
 && useradd -r -u 10001 app
ENV PORT=8000 PATTERN_CONFIG=/app/services/pattern-engine/pattern-engine.example.yaml PATTERN_SPEC_DIR=/app/services/pattern-engine/spec
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:'+os.getenv('PORT','8000')+'/healthz')"
CMD ["python", "-m", "pattern_engine.main"]
