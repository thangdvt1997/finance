# base ghim digest (Renovate cập nhật); lock có hash: services/expert-collector/requirements.lock (infra/ops/lock_deps.sh)
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
WORKDIR /app
COPY services/expert-collector/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock
COPY libs/common /app/libs/common
COPY services/expert-collector /app/services/expert-collector
RUN pip install --no-cache-dir --no-deps /app/libs/common /app/services/expert-collector
ENV PORT=8000
EXPOSE 8000
CMD ["python", "-m", "expert_collector"]
