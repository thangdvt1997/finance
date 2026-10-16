#!/usr/bin/env bash
# CỔNG CHẤT LƯỢNG: smoke test đầu-cuối sau deploy (< 3 phút). Chạy trên VPS: bash infra/ops/smoke.sh [--quiet]
# Việc làm: tạo tài khoản thử qa_stab_s_* (master, chuyên gia, client) -> Playwright trong container tạm (host network) ->
#   đăng nhập 3 vai, mở mọi trang chính (master: mọi mục điều hướng; client: 12 trang), gọi API chính, kiểm tra:
#   không lỗi console/pageerror, không 4xx/5xx/mất kết nối bất thường, không lộ tên nguồn dữ liệu, không NaN/undefined, chuyên gia bị 403 ở API quản trị.
# Chịu deploy giữa chừng: chờ web-ui/client-ui trả lời (tối đa 90s), đăng nhập + mở trang có retry ngắn.
# Thoát 0 = xanh; 1 = có lỗi (in tóm tắt FAIL); 2 = không chạy được hạ tầng smoke. Không in secret; tài khoản thử luôn bị xoá khi xong.
# Biến: SMOKE_MAX_ROUTES (mặc định 60), SMOKE_TIMEOUT (giây, mặc định 210), SMOKE_DEADLINE (ngân sách duyệt trang, mặc định 140), BASE_M/BASE_C.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
Q="$ROOT/tests/qa"
BASE_M="${BASE_M:-http://127.0.0.1:8580}"; BASE_C="${BASE_C:-http://127.0.0.1:8581}"
W=/tmp/qa-s-smoke; TAG=$$
UM=qa_stab_s_m; UE=qa_stab_s_e; UC=999007711
log() { printf '[smoke %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
exec 8>/tmp/tradingsys-smoke.lock
flock -w 300 8 || { log "smoke khác đang chạy quá lâu"; exit 2; }

mkdir -p "$W" && chmod 700 "$W" && rm -rf "$W/out" "$W"/pw_* && cp "$Q/s_smoke.mjs" "$W/"
cleanup() {
  docker exec -i tradingsys-auth python - delete $UM x < "$Q/s_user.py" >/dev/null 2>&1
  docker exec -i tradingsys-auth python - delete $UE x < "$Q/s_user.py" >/dev/null 2>&1
  docker exec -i tradingsys-auth python - delete $UC < "$ROOT/services/client-ui/qa/auth_testacct.py" >/dev/null 2>&1
  docker rm -f "qa-s-smoke-$TAG" >/dev/null 2>&1
  rm -f "$W"/pw_*
}
trap cleanup EXIT
cleanup_pre() { cleanup; }; cleanup_pre

# chờ hạ tầng (deploy giữa chừng)
for i in $(seq 1 18); do
  a=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$BASE_M/" || true); b=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$BASE_C/c/" || true)
  [[ "$a" =~ ^(200|302)$ && "$b" == 200 ]] && break
  [ "$i" = 18 ] && { log "web-ui/client-ui không phản hồi (master=$a client=$b)"; exit 1; }
  sleep 5
done
docker image inspect mcr.microsoft.com/playwright:v1.49.0-jammy >/dev/null 2>&1 || { log "thiếu image playwright:v1.49.0-jammy"; exit 2; }

# tạo tài khoản thử (retry khi auth đang khởi động)
mk() { for i in 1 2 3 4 5 6; do "$@" && return 0; sleep 5; done; return 1; }
mk bash -c "docker exec -i tradingsys-auth python - create $UM master < '$Q/s_user.py' > '$W/pw_m'" || { log "không tạo được master thử"; exit 1; }
mk bash -c "docker exec -i tradingsys-auth python - create $UE expert < '$Q/s_user.py' > '$W/pw_e'" || { log "không tạo được chuyên gia thử"; exit 1; }
mk bash -c "docker exec -i tradingsys-auth python - create $UC < '$ROOT/services/client-ui/qa/auth_testacct.py' | python3 -c 'import sys,json;print(json.load(sys.stdin)[\"passcode\"])' > '$W/pw_c'" || { log "không tạo được client thử"; exit 1; }
chmod 600 "$W"/pw_*

log "chạy kiểm tra trình duyệt (3 vai trò)"
OUTF="$W/out.txt"
timeout "${SMOKE_TIMEOUT:-210}" docker run --rm --name "qa-s-smoke-$TAG" --network host -v "$W:/work" -w /work \
  -e BASE_M="$BASE_M" -e BASE_C="$BASE_C" -e U_M=$UM -e U_E=$UE -e U_C=$UC -e DEADLINE_S="${SMOKE_DEADLINE:-140}" -e MAX_ROUTES="${SMOKE_MAX_ROUTES:-60}" \
  mcr.microsoft.com/playwright:v1.49.0-jammy sh -c '[ -d node_modules/playwright ] || npm i --no-save --silent playwright@1.49.0 >/dev/null 2>&1; node s_smoke.mjs' >"$OUTF" 2>&1
rc=$?
if [ $rc = 124 ]; then log "TIMEOUT smoke (>${SMOKE_TIMEOUT:-210}s)"; tail -5 "$OUTF"; exit 1; fi
grep -E '^(FAIL |\{)' "$OUTF" | sed -E 's/(password|secret|token)=[^ ]+/\1=***/Ig' | head -60
[ $rc = 0 ] && log "SMOKE XANH" || log "SMOKE ĐỎ (mã $rc)"
exit $([ $rc = 0 ] && echo 0 || echo 1)
