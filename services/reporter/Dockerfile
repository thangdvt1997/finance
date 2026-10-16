# Build từ gốc repo: docker build -f services/reporter/Dockerfile .
# Base ghim digest; lock có hash: services/reporter/requirements.lock (infra/ops/lock_deps.sh reporter), chỉ nhận wheel.
# WeasyPrint cần pango (apt) + font có tiếng Việt (DejaVu phủ Latin mở rộng đầy đủ dấu tiếng Việt). Gói apt không ghim (theo snapshot Debian của digest base).
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fontconfig fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*
COPY services/reporter/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes -r /app/requirements.lock
COPY libs/common /app/libs/common
COPY services/reporter /app/services/reporter
RUN pip install --no-cache-dir --no-deps /app/libs/common /app/services/reporter \
 && useradd -r -u 10001 app && mkdir -p /data && chown app /data
# FS gốc chỉ-đọc: cache fontconfig/weasyprint đặt vào tmpfs /tmp
ENV PORT=8000 DATA_DIR=/data XDG_CACHE_HOME=/tmp/.cache HOME=/tmp
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:'+os.getenv('PORT','8000')+'/healthz')"
CMD ["python", "-m", "reporter.main"]
