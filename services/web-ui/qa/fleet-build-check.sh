#!/bin/sh
# Kiểm tra BUILD web-ui trong container node tạm (không deploy, không đụng web-ui đang chạy). Dùng sau khi `deploy.sh ""` (chỉ đồng bộ).
#   sh /root/trading-system/services/web-ui/qa/fleet-build-check.sh [tag]     -> in lỗi build (nếu có) + kích thước chunk; dist ở /tmp/qa-fleet-build-<tag>
set -e
TAG="${1:-x}"; OUT="/tmp/qa-fleet-build-$TAG"; rm -rf "$OUT"; mkdir -p "$OUT"
docker volume create qa-fleet-npmcache >/dev/null
docker run --rm -v /root/trading-system/services/web-ui/app:/src:ro -v qa-fleet-npmcache:/root/.npm -v "$OUT:/out" node:22-alpine \
  sh -c "mkdir /app && cp -r /src/. /app/ && cd /app && npm ci --prefer-offline --no-audit --no-fund >/dev/null 2>&1 && npx vite build --outDir /out --emptyOutDir 2>&1 | tail -40"
