# Build từ gốc repo: docker build -f services/pattern-scan/Dockerfile .
# Lock có hash: services/pattern-scan/requirements.lock (gồm phụ thuộc của libs/common + pattern-render), chỉ nhận wheel.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
WORKDIR /app
COPY services/pattern-scan/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes -r /app/requirements.lock
COPY libs/common /app/libs/common
COPY services/pattern-render /app/services/pattern-render
COPY services/pattern-scan /app/services/pattern-scan
RUN pip install --no-cache-dir --no-deps /app/libs/common /app/services/pattern-render /app/services/pattern-scan \
 && useradd -r -u 10001 app
# matplotlib cần thư mục cache ghi được (container read_only -> /tmp là tmpfs)
ENV PORT=8000 MPLCONFIGDIR=/tmp/mpl MPLBACKEND=Agg PATTERN_SCAN_CONFIG=/app/services/pattern-scan/pattern-scan.example.yaml
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:'+os.getenv('PORT','8000')+'/healthz')"
CMD ["python", "-m", "pattern_scan.main"]
