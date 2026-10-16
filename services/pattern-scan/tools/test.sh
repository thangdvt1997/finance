#!/bin/sh
# Chạy pytest pattern-scan trong container tạm (chỉ mount mã cần thiết, không copy cả repo/dữ liệu).
ROOT="${TS_ROOT:-/root/trading-system}"
docker run --rm -v "$ROOT/libs/common:/s/libs/common:ro" -v "$ROOT/services/pattern-render:/s/services/pattern-render:ro" \
  -v "$ROOT/services/pattern-scan:/s/services/pattern-scan:ro" python:3.12-slim sh -c '
cp -r /s /w && cd /w && pip install -q --disable-pip-version-check --root-user-action=ignore ./libs/common[test] ./services/pattern-render "./services/pattern-scan[test]" >/dev/null 2>&1
cd services/pattern-scan && python -m pytest -q -p no:cacheprovider "$@"' -- "$@"
