#!/usr/bin/env bash
# SMOKE NHANH theo service vừa deploy (<60s). Dùng: bash infra/ops/smoke_quick.sh <svc> [<svc>...]   Thoát 0 xanh / 1 đỏ.
#  - mọi service: container running + healthy, không restart-loop, log 30s gần nhất không bão Traceback/CRITICAL
#  - service có API (không phải hạ tầng thuần): đăng nhập master thử + 8 API chính + anon 401 (tests/qa/s_quick.py, ~5-15s)
#  - web-ui / client-ui / nginx: thêm smoke trình duyệt rút gọn (smoke.sh, 12 trang master/client, ngân sách 40s)
# Smoke ĐẦY ĐỦ (2-3 phút) vẫn là infra/ops/smoke.sh; deploy_local chạy nó tối đa 1 lần/15 phút.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; Q="$ROOT/tests/qa"
BASE_M="${BASE_M:-http://127.0.0.1:8580}"; BASE_C="${BASE_C:-http://127.0.0.1:8581}"
log() { printf '[smoke-quick %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
SVCS=("$@"); [ ${#SVCS[@]} -gt 0 ] || { echo "usage: smoke_quick.sh <svc>..." >&2; exit 2; }
INFRA_ONLY=" timescaledb redis nats prometheus grafana loki promtail jaeger gatus ntfy alertmanager node-exporter cadvisor postgres-exporter redis-exporter "
UI=" web-ui client-ui nginx "
RC=0; NEEDAPI=0; NEEDUI=0
for s in "${SVCS[@]}"; do
  cid=$(docker ps -q --filter "label=com.docker.compose.project=tradingsys" --filter "label=com.docker.compose.service=$s" | head -1)
  if [ -z "$cid" ]; then log "FAIL $s: không có container chạy"; RC=1; continue; fi
  ok=0; for i in 1 2 3 4 5 6; do
    hs=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid"); st=$(docker inspect -f '{{.State.Status}}' "$cid")
    [ "$st" = running ] && [ "$hs" != unhealthy ] && [ "$hs" != starting ] && { ok=1; break; }; sleep 4
  done
  [ $ok = 1 ] || { log "FAIL $s: state=$st health=$hs"; RC=1; continue; }
  r1=$(docker inspect -f '{{.RestartCount}}' "$cid"); sleep 3; r2=$(docker inspect -f '{{.RestartCount}}' "$cid")
  [ "$r1" = "$r2" ] || { log "FAIL $s: đang restart ($r1 -> $r2)"; RC=1; continue; }
  n=$(docker logs --since 30s "$cid" 2>&1 | grep -cE 'Traceback \(most recent|CRITICAL' || true)
  [ "${n:-0}" -le 3 ] || { log "FAIL $s: $n Traceback/CRITICAL trong 30s"; RC=1; continue; }
  case "$INFRA_ONLY" in *" $s "*) ;; *) NEEDAPI=1 ;; esac
  case "$UI" in *" $s "*) NEEDUI=1 ;; esac
  log "$s: running/$hs, ổn định"
done
[ $RC = 0 ] || exit 1
if [ $NEEDAPI = 1 ]; then
  W=$(mktemp -d /tmp/qa-sq.XXXXXX); chmod 700 "$W"; UM="qa_stab_sq_$$"
  trap 'docker exec -i tradingsys-auth python - delete '"$UM"' x < "'"$Q"'/s_user.py" >/dev/null 2>&1; rm -rf "$W"' EXIT
  for i in 1 2 3 4 5 6; do docker exec -i tradingsys-auth python - create "$UM" master < "$Q/s_user.py" >"$W/pw" 2>/dev/null && break; sleep 4; done
  [ -s "$W/pw" ] || { log "FAIL: không tạo được master thử"; exit 1; }
  chmod 600 "$W/pw"
  python3 "$Q/s_quick.py" "$BASE_M" "$W/pw" "$UM" || RC=1
  if [ $NEEDUI = 1 ]; then
    c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$BASE_C/c/" || true); [ "$c" = 200 ] || { log "FAIL client-ui /c/: $c"; RC=1; }
  fi
fi
if [ $NEEDUI = 1 ] && [ $RC = 0 ]; then
  log "smoke trình duyệt rút gọn (12 trang, 40s)"
  SMOKE_MAX_ROUTES=12 SMOKE_DEADLINE=40 SMOKE_TIMEOUT=110 bash "$ROOT/infra/ops/smoke.sh" || RC=1
fi
[ $RC = 0 ] && log "SMOKE NHANH XANH: ${SVCS[*]}" || log "SMOKE NHANH ĐỎ: ${SVCS[*]}"
exit $RC
