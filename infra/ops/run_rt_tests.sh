#!/bin/sh
# K='not e2e' sh run_rt_tests.sh ...  = lọc -k.
# Chạy pytest của api-gateway TRONG container tạm (như run_tests.sh) nhưng cho phép chọn file/ tuỳ chọn: sh run_rt_tests.sh tests/test_realtime.py -q
ROOT="${TS_ROOT:-/root/trading-system}"
mkdir -p /root/qa-e2e/pip
docker run --rm -v "$ROOT:/src:ro" -v /root/qa-e2e/pip:/pip -e PIP_CACHE_DIR=/pip -e A="$*" -e K="$K" python:3.12-slim sh -c '
set -e
mkdir /w && tar -C /src --exclude=./data --exclude=./.git --exclude=node_modules --exclude=./backups --exclude=./wal-archive -cf - . | tar -C /w -xf - && cd /w   # bo data/ (50GB+)
pip install -q --disable-pip-version-check ./libs/common[test] >/dev/null 2>&1
pip install -q --disable-pip-version-check "./services/api-gateway[test]" >/dev/null 2>&1
cd services/api-gateway && python -m pytest -p no:cacheprovider ${K:+-k "$K"} $A 2>&1 | tail -200'
