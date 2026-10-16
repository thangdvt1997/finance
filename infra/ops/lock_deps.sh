#!/bin/sh
# Sinh lockfile có hash cho các service (trong container tạm; không đụng thứ khác). Kết quả: /root/ts-locks/<svc>.requirements.lock
# Dùng:  sh infra/ops/lock_deps.sh [service...]   (mặc định: các service chính). Sau đó chép về repo: services/<svc>/requirements.lock
ROOT="${TS_ROOT:-/root/trading-system}"; OUT=/root/ts-locks; mkdir -p $OUT
S="${*:-storage-writer market-collector news-collector expert-collector mt-bridge alert-service api-gateway analytics}"
docker run --rm -v "$ROOT:/src:ro" -v "$OUT:/out" -v /root/qa-e2e/pip:/pip -e PIP_CACHE_DIR=/pip -e UV_CACHE_DIR=/pip/uv python:3.12-slim \
  sh -c "pip install -q uv >/dev/null 2>&1 && python /src/infra/ops/lock_deps.py /src /out $S"
