# Build tu thu muc goc repo:  docker build -f services/market-collector/Dockerfile -t market-collector .
# base ghim digest (Renovate cập nhật); lock có hash: services/market-collector/requirements.lock (infra/ops/lock_deps.sh)
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY services/market-collector/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock
COPY libs/common /app/libs/common
COPY services/market-collector /app/services/market-collector
RUN pip install --no-deps /app/libs/common && pip install --no-deps "/app/services/market-collector"
# vnstock 4.x khong co tren PyPI cho py3.12 -> cai tu index cua tac gia khi build voi --build-arg WITH_VNSTOCK=1.
# (khong cai duoc -> bo qua, provider vnstock tu tat gon luc chay)
ARG WITH_VNSTOCK=0
RUN if [ "$WITH_VNSTOCK" = "1" ]; then       pip install -U --extra-index-url https://vnstocks.com/api/simple vnstock vnai       || echo "WARN: khong cai duoc vnstock -> provider vnstock se tu tat";     fi
ENV VNSTOCK_TELEMETRY=off
RUN useradd -m app && mkdir -p /data && chown app /data
USER app
ENV PORT=8000 CACHE_DIR=/data/cache STATE_FILE=/data/state.json
EXPOSE 8000
CMD ["python", "-m", "market_collector"]
