# Build từ thư mục gốc repo: docker build -f services/alert-service/Dockerfile .
# base ghim digest (Renovate cập nhật); lock có hash: services/alert-service/requirements.lock (infra/ops/lock_deps.sh)
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
WORKDIR /app
COPY services/alert-service/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock
COPY libs/common /app/libs/common
COPY services/alert-service /app/services/alert-service
RUN pip install --no-cache-dir --no-deps /app/libs/common /app/services/alert-service \
 && useradd -r -u 10001 app
COPY services/alert-service/rules.example.yaml /app/rules.yaml
COPY services/alert-service/routes.example.yaml /app/routes.yaml
ENV RULES_FILE=/app/rules.yaml ROUTES_FILE=/app/routes.yaml PORT=8000
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:'+os.getenv('PORT','8000')+'/healthz')"
CMD ["python", "-m", "alert_service.main"]
