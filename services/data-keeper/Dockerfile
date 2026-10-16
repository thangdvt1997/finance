# Build từ thư mục gốc repo: docker build -f services/data-keeper/Dockerfile .
# Lock có hash: services/data-keeper/requirements.lock (infra/ops/lock_deps.sh data-keeper)
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
WORKDIR /app
COPY services/data-keeper/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock
COPY libs/common /app/libs/common
COPY services/data-keeper /app/services/data-keeper
RUN pip install --no-cache-dir --no-deps /app/libs/common /app/services/data-keeper \
 && useradd -r -u 10001 app
ENV PORT=8000
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:'+os.getenv('PORT','8000')+'/healthz')"
CMD ["python", "-m", "data_keeper.main"]
