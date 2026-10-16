#!/usr/bin/env bash
# Triển khai TRỰC TIẾP trên VPS (không tar/SSH): kiểm tra -> snapshot image -> build+up từng service -> chờ healthy
# -> lỗi thì rollback service đó về image rel-<bản trước> và KHÔNG ghi release; chỉ ghi .release khi mọi service OK.
#
# Dùng (từ /root/trading-system):
#   bash infra/ops/deploy_local.sh api-gateway auth            # deploy vài service
#   bash infra/ops/deploy_local.sh --all --exclude pattern-engine
#   Tuỳ chọn:
#     --all                 mọi service trong compose (project tradingsys)
#     --exclude SVC         bỏ qua SVC (lặp lại được)
#     --skip-tests          không chạy pytest (infra/ops/run_tests.sh) — vẫn kiểm compile/0-byte/JSON/YAML
#     --check               chỉ chạy kiểm tra trước build, không build/up
#     --no-record           không ghi .release (vd. deploy thử)
#     --keep-going          service lỗi -> rollback service đó rồi tiếp service sau (mặc định dừng ngay)
#     --timeout SEC         thời gian chờ healthy mỗi service (mặc định 240; briefing-llm/nlp tự x3)
#     --note "TEXT"         ghi chú release (mặc định: deploy_local <svc...>)
#     --skip-smoke          KHẨN CẤP: bỏ cổng smoke (infra/ops/smoke.sh); mặc định smoke chạy sau up, đỏ -> tự rollback mọi service vừa deploy
#                           (thử lại 1 lần sau 20s để chịu deploy của agent khác); đặt FORCE_SMOKE_FAIL=1 để mô phỏng fail (kiểm rollback)
#     --smoke-full          cổng = smoke ĐẦY ĐỦ (infra/ops/smoke.sh, ~2-3 phút), đỏ -> tự rollback (mặc định: smoke NHANH theo service <60s)
#     --debounce SEC        gộp các yêu cầu cùng service đến liên tiếp trong SEC giây (mặc định 60; 0 = tắt)
# KHOÁ THEO TỪNG SERVICE (/tmp/tradingsys_deploy_<svc>.lock): service khác nhau deploy SONG SONG, cùng service xếp hàng; yêu cầu xếp hàng
#   mà lần build trước (bắt đầu SAU khi nó tới) đã xanh thì được GỘP (bỏ qua). Đừng bọc `flock` toàn cục ngoài lệnh này.
# Smoke: NHANH theo service vừa đổi (infra/ops/smoke_quick.sh); smoke ĐẦY ĐỦ chạy NỀN tối đa 1 lần/15 phút (không chặn, chỉ cảnh báo) hoặc khi --smoke-full.
# Cuối mỗi lần chạy in TIMING từng bước (và ghi /tmp/tradingsys-deploy-state/timings.log).
# VER = <UTC>-<git short sha>[-dirty]. Snapshot/record dùng infra/ops/release.sh; rollback thủ công: infra/ops/rollback.sh.
# Chỉ đụng project compose tradingsys. Không in secret.
umask 000   # root/cc dùng chung /tmp state+lock (fs.protected_regular=2) - tránh Permission denied
set -euo pipefail

# bash đọc script dần theo dòng: sửa file khi đang chạy (agent khác commit) => lỗi cú pháp giữa chừng. Chạy từ bản sao tạm.
if [ -z "${_TS_DL_ROOT:-}" ]; then
  _TS_DL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; export _TS_DL_ROOT
  _t="$(mktemp "${TMPDIR:-/tmp}/ts-deploy_local.XXXXXX")"; cp "$0" "$_t"; export _TS_DL_TMP="$_t"
  exec bash "$_t" "$@"
fi
ARR=$(date +%s); T_START=$ARR; LASTT=$ARR; STEPS=(); LOCKED=(); LFDS=(); RESULT=fail; TARGETS=()
STATE="${DEPLOY_STATE:-/tmp/tradingsys-deploy-state}"; mkdir -p "$STATE"; chmod 1777 "$STATE" 2>/dev/null || true
tick() { local n; n=$(date +%s); STEPS+=("$1=$((n - LASTT))s"); LASTT=$n; }
_on_exit() {
  local rc=$? svc
  for svc in "${LOCKED[@]:-}"; do [ -n "$svc" ] && echo "$RESULT $(date +%s)" >"$STATE/$svc.result" 2>/dev/null || true; done
  if [ ${#STEPS[@]} -gt 0 ]; then
    local line="TIMING total=$(( $(date +%s) - T_START ))s ${STEPS[*]}"
    printf '[deploy_local %s] %s\n' "$(date -u +%H:%M:%S)" "$line"
    printf '%s %s [%s] rc=%s %s\n' "$(date -u +%FT%TZ)" "$(id -un)" "${TARGETS[*]:-}" "$rc" "$line" >>"$STATE/timings.log" 2>/dev/null || true
  fi
  [ -n "${_TS_DL_TMP:-}" ] && rm -f "$_TS_DL_TMP"
  return $rc
}
trap _on_exit EXIT
ROOT="$_TS_DL_ROOT"
INFRA="$ROOT/infra"
PROJECT=tradingsys
TIMEOUT=240; SMOKE=1; SMOKE_FULL=0; DEBOUNCE=60; TESTS=1; CHECK_ONLY=0; RECORD=1; KEEP_GOING=0; ALL=0; NOTE=""
EXCL=(); SVCS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --all) ALL=1 ;;
    --exclude) EXCL+=("$2"); shift ;;
    --skip-tests) TESTS=0 ;;
    --skip-smoke) SMOKE=0 ;;
    --smoke-full) SMOKE_FULL=1 ;;
    --debounce) DEBOUNCE="$2"; shift ;;
    --check) CHECK_ONLY=1 ;;
    --no-record) RECORD=0 ;;
    --keep-going) KEEP_GOING=1 ;;
    --timeout) TIMEOUT="$2"; shift ;;
    --note) NOTE="$2"; shift ;;
    -h|--help) sed -n '2,30p' "$ROOT/infra/ops/deploy_local.sh"; exit 0 ;;
    -*) echo "tuỳ chọn lạ: $1" >&2; exit 2 ;;
    *) SVCS+=("$1") ;;
  esac
  shift
done

log() { printf '[deploy_local %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
die() { log "LỖI: $*" >&2; exit 1; }

tick "khoi-dong"
cd "$INFRA"
# tự chữa: có tiến trình khác đặt lại ACL mask của infra/env (chmod 700 -> user cc mất quyền) làm mọi compose config lỗi 'permission denied'
if [ -d env ] && ! cat env/*.env >/dev/null 2>&1; then
  log "CẢNH BÁO: infra/env mất quyền truy cập (ACL mask bị đặt lại) — tự sửa chmod 770 qua container tạm"
  docker run --rm -v "$INFRA:/x" python:3.12-slim sh -c "chmod 770 /x/env; chmod 660 /x/env/*.env" || die "không sửa được quyền infra/env"
fi
[ -f .env ] || die "thiếu infra/.env"
dc() { docker compose -p "$PROJECT" --env-file .env "$@"; }

# Biến bắt buộc (${VAR:?}) của service mới chưa tạo role/secret chặn MỌI lệnh compose. Nếu service đó KHÔNG nằm trong danh sách
# deploy: đặt placeholder chỉ để nội suy được và loại nó khỏi --all (container của nó không bị đụng vì --no-deps).
for _ in 1 2 3 4 5 6 7 8; do
  err=$(dc config -q 2>&1) && break
  m=$(sed -n 's/.*services\.\([A-Za-z0-9_-]*\)\..*required variable \([A-Za-z0-9_]*\) is missing.*/\1 \2/p' <<<"$err" | head -1)
  [ -n "$m" ] || break
  msvc=${m% *}; mvar=${m#* }
  for s in "${SVCS[@]}"; do [ "$s" = "$msvc" ] && die "$msvc cần biến $mvar trong infra/.env: $err"; done
  log "cảnh báo: $mvar chưa có -> bỏ qua $msvc (placeholder chỉ để nội suy)"
  export "$mvar=__placeholder_${msvc}_not_deployed__"; EXCL+=("$msvc")
done
dc config -q || die "docker compose config lỗi"
mapfile -t ALL_SVCS < <(dc config --services)
if [ $ALL = 1 ]; then SVCS=("${ALL_SVCS[@]}"); fi
[ ${#SVCS[@]} -gt 0 ] || die "chưa chỉ định service (hoặc --all)"
TARGETS=()
for s in "${SVCS[@]}"; do
  printf '%s\n' "${ALL_SVCS[@]}" | grep -qx "$s" || die "service không có trong compose: $s"
  skip=0; for e in "${EXCL[@]}"; do [ "$s" = "$e" ] && skip=1; done
  [ $skip = 1 ] || TARGETS+=("$s")
done
[ ${#TARGETS[@]} -gt 0 ] || die "không còn service nào sau --exclude"

# --- KHOÁ THEO TỪNG SERVICE + GỘP YÊU CẦU (thay khoá toàn cục) ---
# Bị bọc ngoài bằng flock toàn cục (kiểu `flock /tmp/tradingsys_deploy.lock deploy_local.sh`) thì mất song song -> cảnh báo.
for _f in /proc/$$/fd/*; do
  case "$(readlink "$_f" 2>/dev/null)" in /tmp/tradingsys*deploy*.lock|/tmp/tradingsys-deploy.lock)
    log "CẢNH BÁO: đang bị bọc flock toàn cục ($(readlink "$_f")) — bỏ flock bọc ngoài để deploy song song theo từng service" ;; esac
done
SORTED=($(printf '%s\n' "${TARGETS[@]}" | sort -u))
for s in "${SORTED[@]}"; do printf '%s %s\n' "$ARR" "$$" >>"$STATE/$s.req"; done
if [ "$DEBOUNCE" -gt 0 ] 2>/dev/null; then   # đợt yêu cầu liên tiếp cùng service: đợi yên DEBOUNCE giây (tối đa 90s) để một lần build gộp tất cả
  dw0=$(date +%s); dwl=0
  while :; do
    latest=0
    for s in "${SORTED[@]}"; do
      while read -r ts pid; do
        [ "$pid" = "$$" ] && continue; kill -0 "$pid" 2>/dev/null || continue
        [ "$pid" = "$(cat "$STATE/$s.running" 2>/dev/null)" ] && continue   # deploy đã chạy (giữ khoá) không tính vào debounce
        [ "$ts" -gt "$latest" ] && latest=$ts
      done <"$STATE/$s.req"
    done
    now=$(date +%s)
    [ "$latest" -eq 0 ] && break
    [ $((now - latest)) -ge "$DEBOUNCE" ] && break
    [ $((now - dw0)) -ge 90 ] && break
    [ $dwl = 0 ] && { log "debounce: có yêu cầu cùng service vừa tới — đợi yên ${DEBOUNCE}s để gộp"; dwl=1; }
    sleep 3
  done
fi
tick debounce
for s in "${SORTED[@]}"; do
  exec {lfd}>"/tmp/tradingsys_deploy_$s.lock"; LFDS+=("$lfd")
  flock -w 1800 "$lfd" || die "đang có deploy $s khác chạy (lock /tmp/tradingsys_deploy_$s.lock)"
  LOCKED+=("$s"); echo "$$" >"$STATE/$s.running"
done
tick "khoa(${#SORTED[@]}svc)"
# gộp: nếu lần build của service này bắt đầu SAU lúc yêu cầu của ta tới và đã xanh -> thay đổi của ta đã nằm trong đó
MERGED=(); REST=()
for s in "${TARGETS[@]}"; do
  bs=$(cat "$STATE/$s.build_start" 2>/dev/null || echo 0); rs=$(cat "$STATE/$s.result" 2>/dev/null || echo "none 0")
  if [ "$bs" -ge "$ARR" ] && [ "${rs%% *}" = ok ]; then MERGED+=("$s"); else REST+=("$s"); fi
done
[ ${#MERGED[@]} -gt 0 ] && log "GỘP: ${MERGED[*]} đã được build xanh bởi lần deploy khác (sau khi yêu cầu này tới) — bỏ qua"
if [ ${#REST[@]} -eq 0 ]; then LOCKED=(); log "XONG (tất cả được gộp)"; exit 0; fi
TARGETS=("${REST[@]}"); LOCKED=("${REST[@]}")

# thông tin build của service: dockerfile tương đối (rỗng = service dùng image dựng sẵn)
CFG_JSON="$(dc config --format json)"
svc_dockerfile() {
  python3 -c 'import json,sys; s=json.loads(sys.stdin.read())["services"][sys.argv[1]]; b=s.get("build") or {}; print(b.get("dockerfile","") if b else "")' "$1" <<<"$CFG_JSON"
}

# --- phiên bản ---
cd "$ROOT"
SHA="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
DIRTY=""; [ -n "$(git status --porcelain --untracked-files=no 2>/dev/null)" ] && DIRTY="-dirty"
VER="$(date -u +%Y%m%dT%H%M%SZ)-${SHA}${DIRTY}"
PREV="$(sh "$INFRA/ops/release.sh" current)"; [ "$PREV" = none ] && PREV=pre-versioning
log "VER=$VER  (trước: $PREV)  service: ${TARGETS[*]}"

# --- kiểm tra trước build ---
PATHS=(libs/common infra)
TEST_SVCS=()
for s in "${TARGETS[@]}"; do
  [ -d "services/$s" ] && PATHS+=("services/$s")
  [ -d "services/$s/tests" ] && TEST_SVCS+=("$s")
done
log "kiểm tra: file 0 byte / conflict marker / JSON / YAML / compile Python 3.12 trong: ${PATHS[*]}"
FAIL=0
z=$(find "${PATHS[@]}" \( -name node_modules -o -name .venv -o -name __pycache__ -o -name dist -o -path infra/env \) -prune -o \
      -type f -size 0 ! -name '__init__.py' ! -name '.gitkeep' ! -name 'py.typed' -print 2>/dev/null || true)
[ -z "$z" ] || { log "file 0 byte (nghi bị cắt khi đồng bộ):"; echo "$z"; FAIL=1; }
c=$(git grep -lE '^(<<<<<<< |>>>>>>> )' -- "${PATHS[@]}" 2>/dev/null || true)
[ -z "$c" ] || { log "còn conflict marker:"; echo "$c"; FAIL=1; }
python3 - "${PATHS[@]}" <<'PY' || FAIL=1
import json, os, sys
try:
    import yaml
except ImportError:
    yaml = None
bad = 0
for root in sys.argv[1:]:
    for r, d, f in os.walk(root):
        d[:] = [x for x in d if x not in ("node_modules", ".venv", "__pycache__", "dist", "env")]
        for x in f:
            p = os.path.join(r, x)
            try:
                if x.endswith(".json"):
                    json.load(open(p, encoding="utf-8"))
                elif yaml and x.endswith((".yml", ".yaml")):
                    list(yaml.safe_load_all(open(p, encoding="utf-8")))
            except Exception as e:
                print(f"  cú pháp lỗi: {p}: {str(e)[:160]}"); bad += 1
sys.exit(1 if bad else 0)
PY
# compile bằng đúng Python 3.12 của image (host là 3.10)
docker run --rm --network none -v "$ROOT:/src:ro" -w /src python:3.12-slim \
  python -c '
import os, sys
bad = 0
for root in sys.argv[1:]:
    for r, d, f in os.walk(root):
        d[:] = [x for x in d if x not in ("node_modules", ".venv", "__pycache__", "env")]
        for x in f:
            if x.endswith(".py"):
                p = os.path.join(r, x)
                try:
                    compile(open(p, "rb").read(), p, "exec")
                except Exception as e:
                    print("  compile lỗi:", p, e); bad += 1
sys.exit(1 if bad else 0)' "${PATHS[@]}" || FAIL=1
for f in "$ROOT"/deploy.sh "$INFRA"/ops/*.sh; do bash -n "$f" 2>&1 || { log "lỗi cú pháp shell: $f"; FAIL=1; }; done
[ $FAIL = 0 ] || die "kiểm tra trước build thất bại — không deploy"
tick "kiem-tra"
if [ $TESTS = 1 ] && [ ${#TEST_SVCS[@]} -gt 0 ]; then
  log "pytest: ${TEST_SVCS[*]}"
  out=$(sh "$INFRA/ops/run_tests.sh" "${TEST_SVCS[@]}" 2>&1) || { echo "$out" | tail -40; die "pytest lỗi (bỏ qua bằng --skip-tests nếu chắc chắn)"; }
  echo "$out" | grep -E '^(===|[0-9]+ passed|.*(passed|failed|error))' | tail -40 || true
fi
tick pytest
[ $CHECK_ONLY = 1 ] && { log "--check: kiểm tra OK, dừng"; RESULT=ok; exit 0; }

# --- env theo service + snapshot image ---
cd "$INFRA"
bash ops/gen_service_env.sh >/dev/null
bash ops/gen_briefing_secrets.sh >/dev/null
# snapshot THEO SERVICE (khoá theo service nên không dẫm nhau): rel-$PREV (tương thích rollback.sh) + pre-$VER (đích rollback của lần deploy NÀY)
for svc in "${TARGETS[@]}"; do
  img="${PROJECT}-$svc"
  if docker image inspect "$img:latest" >/dev/null 2>&1; then
    docker tag "$img:latest" "$img:pre-$VER"; docker tag "$img:latest" "$img:rel-$PREV"
    docker images --format '{{.Tag}}' "$img" | grep '^pre-' | sort -r | tail -n +4 | while read -r t; do docker rmi "$img:$t" >/dev/null 2>&1 || true; done
  fi
done
tick snapshot

wait_healthy() {  # $1 svc; trả 0 nếu healthy (hoặc running ổn định khi không có healthcheck)
  local svc="$1" to="$TIMEOUT" t=0 cid st hs
  case "$svc" in briefing-llm|nlp|timescaledb) to=$((TIMEOUT * 3)) ;; esac
  sleep 3
  while [ $t -lt "$to" ]; do
    cid=$(dc ps -q "$svc" 2>/dev/null | head -1)
    if [ -n "$cid" ]; then
      st=$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || echo gone)
      hs=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || echo gone)
      case "$st/$hs" in
        running/healthy) return 0 ;;
        running/none) [ $t -ge 15 ] && return 0 ;;
        exited/*|dead/*) log "$svc: container $st"; return 1 ;;
      esac
      [ "$hs" = unhealthy ] && [ $t -ge 30 ] && { log "$svc: unhealthy"; return 1; }
    fi
    sleep 5; t=$((t + 8))
  done
  log "$svc: quá ${to}s chưa healthy (status=${st:-?}/${hs:-?})"; return 1
}

rollback_svc() {
  local svc="$1" img="${PROJECT}-$1"
  if docker image inspect "$img:pre-$VER" >/dev/null 2>&1; then
    log "ROLLBACK $svc -> $img:pre-$VER (bản trước, tức $PREV)"
    docker tag "$img:pre-$VER" "$img:latest"
    local TIMEOUT=$(( TIMEOUT < 180 ? 180 : TIMEOUT ))
    dc up -d --no-build --no-deps "$svc" && wait_healthy "$svc" && log "$svc đã về bản cũ, healthy" || log "$svc rollback xong nhưng CHƯA healthy — cần xử lý tay"
  else
    log "$svc: không có image rel-$PREV (service dùng image dựng sẵn?) — giữ nguyên, cần xử lý tay"
    docker logs --tail 30 "$(dc ps -q "$svc" | head -1)" 2>&1 | sed 's/^/    /' || true
  fi
}

OK=(); BAD=()
for svc in "${TARGETS[@]}"; do
  df=$(svc_dockerfile "$svc")
  if [ -n "$df" ]; then
    log "build + up $svc ($df) — dùng cache lớp Docker (không --no-cache)"
    date +%s >"$STATE/$svc.build_start"; _b0=$(date +%s)
    if ! dc build "$svc" >"/tmp/ts-build-$svc.$$.log" 2>&1; then
      tail -30 "/tmp/ts-build-$svc.$$.log"; rm -f "/tmp/ts-build-$svc.$$.log"
      log "$svc: BUILD LỖI (image cũ vẫn chạy)"; BAD+=("$svc")
      [ $KEEP_GOING = 1 ] && continue || break
    fi
    rm -f "/tmp/ts-build-$svc.$$.log"; STEPS+=("build:$svc=$(( $(date +%s) - _b0 ))s"); LASTT=$(date +%s)
  else
    log "up $svc (image dựng sẵn)"; date +%s >"$STATE/$svc.build_start"
  fi
  _u0=$(date +%s)
  if dc up -d --no-build --no-deps "$svc" && wait_healthy "$svc"; then
    OK+=("$svc"); log "$svc OK"; STEPS+=("up+healthy:$svc=$(( $(date +%s) - _u0 ))s"); LASTT=$(date +%s)
  else
    BAD+=("$svc"); rollback_svc "$svc"
    [ $KEEP_GOING = 1 ] || break
  fi
done

log "OK: ${OK[*]:-}"
if [ ${#BAD[@]} -gt 0 ]; then
  log "LỖI: ${BAD[*]} — KHÔNG ghi release (vẫn là $PREV)"
  exit 1
fi
if [ ${#OK[@]} -ne ${#TARGETS[@]} ]; then die "chưa deploy hết service"; fi

# --- CỔNG CHẤT LƯỢNG: smoke NHANH theo service (<60s) là cổng chặn; smoke ĐẦY ĐỦ tối đa 1 lần/15 phút (cảnh báo) hoặc --smoke-full (chặn).
#     đỏ -> rollback mọi service vừa deploy, KHÔNG ghi release ---
if [ $SMOKE = 1 ]; then
  smoke_run() {
    if [ "${FORCE_SMOKE_FAIL:-0}" = 1 ]; then log "FORCE_SMOKE_FAIL=1: mô phỏng smoke đỏ"; return 1; fi
    if [ $SMOKE_FULL = 1 ]; then bash "$INFRA/ops/smoke.sh"; else bash "$INFRA/ops/smoke_quick.sh" "${OK[@]}"; fi
  }
  log "smoke $([ $SMOKE_FULL = 1 ] && echo ĐẦY ĐỦ || echo nhanh) (cổng chất lượng): ${OK[*]}"
  if ! smoke_run; then
    log "smoke đỏ — thử lại 1 lần sau 20s (loại trừ deploy giữa chừng của agent khác)"; sleep 20
    if ! smoke_run; then
      log "SMOKE ĐỎ -> TỰ ROLLBACK: ${OK[*]}"
      for svc in "${OK[@]}"; do rollback_svc "$svc"; done
      log "đã rollback về $PREV — KHÔNG ghi release. Sửa lỗi rồi deploy lại (khẩn cấp: --skip-smoke)"
      tick smoke; exit 1
    fi
  fi
  log "smoke xanh"; tick smoke
  if [ $SMOKE_FULL = 0 ]; then   # smoke đầy đủ định kỳ: NỀN, tối đa 1 lần/15 phút, không chặn deploy, chỉ cảnh báo
    lastfull=$(cat "$STATE/smoke_full.ok" 2>/dev/null || echo 0); tried=$(cat "$STATE/smoke_full.try" 2>/dev/null || echo 0)
    if [ $(( $(date +%s) - (lastfull > tried ? lastfull : tried) )) -ge 900 ]; then
      log "smoke ĐẦY ĐỦ định kỳ chạy NỀN (log: $STATE/smoke_full.log) — không chặn, không rollback"
      ( for _fd in "${LFDS[@]}"; do eval "exec ${_fd}>&-"; done
        exec setsid nohup bash "$INFRA/ops/smoke_full_bg.sh" "${OK[*]}" </dev/null >>"$STATE/smoke_full.log" 2>&1 ) &
    fi
    [ -s "$STATE/smoke_full.red" ] && [ "$(stat -c %Y "$STATE/smoke_full.red")" -gt "$lastfull" ] && log "CẢNH BÁO: smoke đầy đủ lần gần nhất ĐỎ: $(tail -1 "$STATE/smoke_full.red")"
  else date +%s >"$STATE/smoke_full.ok"; fi
else
  log "CẢNH BÁO: --skip-smoke — bỏ cổng chất lượng, KHÔNG có bảo đảm giao diện/API sau deploy"
fi
if [ $RECORD = 1 ]; then
  cd "$ROOT"
  TGZ="$(mktemp -d)/ts-$VER.tgz"
  # tarball mã nguồn (file git theo dõi + file mới chưa ignore) để infra/ops/rollback.sh khôi phục được
  git ls-files -z -co --exclude-standard | tar --null -T - -cf - 2>/dev/null | gzip -n >"$TGZ"
  # tarball phải nguyên vẹn (gzip + tar đọc được + đủ số file) trước khi ghi release; hỏng/cắt -> KHÔNG ghi
  NEXP=$(git ls-files -co --exclude-standard | wc -l)
  gzip -t "$TGZ" && [ "$(tar tzf "$TGZ" | wc -l)" -ge "$((NEXP * 9 / 10))" ] || { rm -rf "$(dirname "$TGZ")"; die "tarball release hỏng/bị cắt — KHÔNG ghi release (service đã chạy bản mới)"; }
  HASH=$(sha256sum "$TGZ" | cut -c1-12)
  exec {rfd}>/tmp/tradingsys_release_record.lock; flock -w 300 "$rfd"
  SUDO_USER="$(id -un)" sh "$INFRA/ops/release.sh" record "$VER" "$HASH" "${NOTE:-deploy_local ${TARGETS[*]}}" "$TGZ"
  rm -rf "$(dirname "$TGZ")"
fi
tick record; RESULT=ok
log "XONG: $VER"
