#!/usr/bin/env bash
# Smoke ĐẦY ĐỦ chạy NỀN (do deploy_local.sh gọi tối đa 1 lần/15 phút). Không chặn deploy, không rollback; kết quả ở /tmp/tradingsys-deploy-state/smoke_full.{ok,red,log}
# Dùng: bash infra/ops/smoke_full_bg.sh "<service vừa deploy>"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; STATE="${DEPLOY_STATE:-/tmp/tradingsys-deploy-state}"
exec 7>/tmp/tradingsys_smoke_full.lock; flock -n 7 || { echo "smoke đầy đủ đang chạy — bỏ qua"; exit 0; }
last=$(cat "$STATE/smoke_full.ok" 2>/dev/null || echo 0); tried=$(cat "$STATE/smoke_full.try" 2>/dev/null || echo 0)
[ $(( $(date +%s) - (last > tried ? last : tried) )) -ge 900 ] || exit 0
date +%s >"$STATE/smoke_full.try"
echo "[$(date -u +%FT%TZ)] smoke đầy đủ sau deploy: $1"
if bash "$ROOT/infra/ops/smoke.sh"; then date +%s >"$STATE/smoke_full.ok"; echo "XANH"
else echo "$(date -u +%FT%TZ) ĐỎ sau deploy: $1" >>"$STATE/smoke_full.red"; echo "ĐỎ — xem log; ghi vào docs/handoff/QA_ISSUES.md nếu là lỗi thật"; fi
