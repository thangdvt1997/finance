#!/bin/sh
# Chạy pytest của libs/common và/hoặc các service TRONG container tạm trên VPS (không cần Python trên host, không đụng container tradingsys).
# Dùng:  sh infra/ops/run_tests.sh common storage-writer mt-bridge     (mặc định: common storage-writer)
# Ghi chú: cài tscommon + service + extras [test]; pip cache ở /root/qa-e2e/pip. Mã lấy từ /root/trading-system (đã deploy.sh).
ROOT="${TS_ROOT:-/root/trading-system}"
T="${*:-common storage-writer}"
mkdir -p /root/qa-e2e/pip
docker run --rm -v "$ROOT:/src:ro" -v /root/qa-e2e/pip:/pip -e PIP_CACHE_DIR=/pip -e T="$T" python:3.12-slim sh -c '
set -e
mkdir /w && tar -C /src --exclude=./data --exclude=./.git --exclude=node_modules --exclude=./backups --exclude=./wal-archive -cf - . | tar -C /w -xf - && cd /w   # bỏ data/ (GB) cho nhanh
pip install -q --disable-pip-version-check ./libs/common[test] >/dev/null 2>&1 || pip install -q ./libs/common[test]
rc=0
for t in $T; do
  if [ "$t" = common ]; then d=libs/common; else d=services/$t; fi
  echo "=== $t ==="
  [ "$t" = pattern-scan ] && pip install -q --disable-pip-version-check ./services/pattern-render >/dev/null 2>&1  # phụ thuộc nội bộ
  pip install -q --disable-pip-version-check "./$d[test]" >/dev/null 2>&1 || pip install -q "./$d[test]" 2>&1 | tail -3
  (cd $d && python -m pytest -q -x -p no:cacheprovider >/tmp/pt.out 2>&1); r=$?; tail -15 /tmp/pt.out; [ $r -eq 0 ] || rc=1
done
exit $rc'
