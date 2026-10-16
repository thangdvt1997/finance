#!/usr/bin/env bash
# CI chạy NGAY TRÊN VPS (không cần git server): ruff + pytest từng package + quét tĩnh "không có mã đặt lệnh" + trivy fs + SBOM syft cho image đang chạy.
# Dùng sau deploy.sh:  sh infra/ops/ci_vps.sh [quick]     (quick = chỉ ruff + pytest). Báo cáo ở /var/tmp/tradingsys-ci/. Thoát !=0 nếu ruff/pytest/static scan lỗi.
set -u -o pipefail   # pipefail: ruff/scan loi trong pipe `| tail || rc=1` phai lam CI do
ROOT="${TS_ROOT:-/root/trading-system}"; OUT="${CI_OUT:-/var/tmp/tradingsys-ci}"; mkdir -p "$OUT" 2>/dev/null; [ -w "$OUT" ] || OUT="$(mktemp -d)"; rc=0
echo "== ruff =="; docker run --rm -v "$ROOT:/src:ro" -w /src ghcr.io/astral-sh/ruff:0.8.6 check --no-cache . 2>&1 | tail -25 || rc=1
echo "== bash -n (cú pháp script shell) =="; for f in "$ROOT"/deploy.sh "$ROOT"/infra/ops/*.sh "$ROOT"/infra/*/*.sh; do [ -f "$f" ] && { bash -n "$f" 2>&1 || { echo "  LỖI: $f"; rc=1; }; }; done
echo "== pytest =="; sh "$ROOT/infra/ops/run_tests.sh" common storage-writer mt-bridge alert-service api-gateway market-collector news-collector expert-collector analytics pattern-engine paper-trader nlp alert-rules risk-monitor reporter 2>&1 | tee "$OUT/pytest.log" | grep -E "^===|passed|failed|error" || rc=1
grep -q -E "failed|error" "$OUT/pytest.log" && rc=1
echo "== static read-only scan =="; docker run --rm -v "$ROOT:/src:ro" -w /src python:3.12-slim python tests/e2e/static_readonly_scan.py 2>&1 | tail -3 || rc=1
[ "${1:-}" = quick ] && exit $rc
echo "== trivy fs (HIGH,CRITICAL, bỏ qua lỗi chưa có bản vá) =="
docker run --rm -v tradingsys-trivy-cache:/root/.cache -v "$ROOT:/src:ro" aquasec/trivy:0.75.0 fs --quiet --scanners vuln,secret --severity HIGH,CRITICAL --ignore-unfixed /src --skip-dirs /src/research --skip-dirs /src/services/web-ui/app/node_modules 2>&1 | tail -30
echo "== SBOM (syft) =="
for img in $(docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^tradingsys-[a-z-]+:latest$'); do
  f="$OUT/sbom-$(echo "$img" | tr '/:' '__').cdx.json"
  docker run --rm -v /var/run/docker.sock:/var/run/docker.sock:ro anchore/syft:v1.18.1 "$img" -o cyclonedx-json -q > "$f" 2>/dev/null && echo "  $f ($(du -h "$f" | cut -f1))"
done
exit $rc
