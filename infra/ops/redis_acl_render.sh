#!/usr/bin/env bash
# Sinh infra/redis/users.acl (CHỈ chứa băm sha256 của mật khẩu, không chứa mật khẩu rõ) từ infra/.env.
# Thiếu REDIS_*_PASSWORD trong .env thì sinh ngẫu nhiên (hex 48) và THÊM vào .env (sao lưu .env vào <SECRETS_DIR>-bak, 0700).
# Người dùng:
#   ts_admin    toàn quyền (ops, e2e, healthcheck)           REDIS_ADMIN_PASSWORD
#   ts_app      mọi service (stream/string/hash/list/pubsub), CẤM @dangerous @admin @scripting (FLUSHALL, CONFIG, KEYS, DEBUG, SHUTDOWN, EVAL...)  REDIS_APP_PASSWORD
#   ts_gateway  api-gateway: CHỈ ĐỌC                         REDIS_GATEWAY_PASSWORD
#   ts_metrics  redis-exporter: chỉ INFO/CONFIG GET/SLOWLOG/XINFO/XLEN/XPENDING/SCAN... (không đọc/ghi dữ liệu)  REDIS_METRICS_PASSWORD
#   ts_cache    cache phản hồi api-gateway (redis-cache): CHỈ GET/SET/MGET/DEL/UNLINK/EXPIRE/INCR... trên key `cache:*`, KHÔNG đọc stream, KHÔNG SCAN  REDIS_CACHE_PASSWORD
#   ts_trackrec service track-record: CHỈ key `tr:*` (HSET/HGETALL/DEL/GET/SET/EXPIRE...), không stream/pubsub  REDIS_TRACKREC_PASSWORD
#   (expert-collector dùng ts_app: ĐỌC `tr:weights`/`tr:weights:ts` do ts_trackrec ghi — chỉ đọc theo quy ước mã nguồn trackweights.py; ts_app ~* nên không cần user riêng)
#   ts_svc_<service>  user RIÊNG từng service, luật từ infra/ops/redis_acl_services.manifest (HARDENING §7.2)  REDIS_SVC_<SERVICE>_PASSWORD
#   default     tắt (mặc định DEFAULT_OFF=1 từ 2026-10-14; DEFAULT_OFF=0 chỉ để gỡ rối).
# Tuỳ chọn:  --load   nạp lại ACL vào redis đang chạy (ACL LOAD qua ts_admin; file lỗi -> redis giữ ACL cũ, không restart)
#            --check  ACL DRYRUN: lệnh mong đợi của từng ts_svc_* phải OK, lệnh ngoài phạm vi phải bị từ chối (không ghi gì)
# Chạy được bằng user không phải root: sao lưu .env vào $HOME/.tradingsys-secrets-bak nếu không ghi được <SECRETS_DIR>-bak.
set -euo pipefail
cd "$(dirname "$0")/.."
DEFAULT_OFF="${DEFAULT_OFF:-1}"
MANIFEST=ops/redis_acl_services.manifest
REDIS_CTR="${REDIS_CTR:-tradingsys-redis-1}"
envget() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
# danh sách "service|user|PASSVAR|luật" từ manifest
svc_rules() { [ -f "$MANIFEST" ] || return 0; tr -d '\r' < "$MANIFEST" | grep -E '^[a-z0-9-]+:' | while IFS= read -r line; do
  s="${line%%:*}"; r="${line#*:}"; r="$(echo "$r" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
  u="ts_svc_$(echo "$s" | tr '-' '_')"; v="REDIS_SVC_$(echo "$s" | tr 'a-z-' 'A-Z_')_PASSWORD"; printf '%s|%s|%s|%s\n' "$s" "$u" "$v" "$r"; done; }
admin_cli() { envget REDIS_ADMIN_PASSWORD | docker exec -i "$REDIS_CTR" sh -c 'read -r p; REDISCLI_AUTH="$p" redis-cli --no-auth-warning --user ts_admin "$@"' sh "$@"; }
if [ "${1:-}" = "--check" ]; then
  set -f   # không glob "*" trong lệnh mẫu
  # Lệnh mẫu: key đầu tiên của từng selector + lệnh trong selector; thêm lệnh cấm (FLUSHALL, KEYS, XADD vào stream không thuộc service, GET khoá ngoài phạm vi).
  fail=0
  while IFS='|' read -r s u v r; do
    for sel in $(echo "$r" | grep -oE '\([^)]*\)' | tr ' ' '#'); do
      sel="${sel#(}"; sel="${sel%)}"; keys=$(echo "$sel" | tr '#' '\n' | grep -E '^%?[RW]?~' | sed -E 's/^%?[RW]?~//; s/\*$/x/'); cmds=$(echo "$sel" | tr '#' '\n' | grep -E '^\+')
      k=$(echo "$keys" | head -1)
      for c in $cmds; do c="${c#+}"
        case "$c" in
          xadd) a="XADD $k * e x";; xreadgroup) a="XREADGROUP GROUP g c COUNT 1 STREAMS $k >";; xack) a="XACK $k g 0-1";;
          xgroup\|create) a="XGROUP CREATE $k g \$ MKSTREAM";; xgroup\|delconsumer) a="XGROUP DELCONSUMER $k g c";; xautoclaim) a="XAUTOCLAIM $k g c 1000 0";;
          xpending) a="XPENDING $k g";; xinfo\|groups) a="XINFO GROUPS $k";; xinfo\|consumers) a="XINFO CONSUMERS $k g";; xinfo\|stream) a="XINFO STREAM $k";;
          xlen|xrevrange|xrange) a="$(echo $c | tr a-z A-Z) $k"; [ "$c" = xlen ] || a="$a + -"; [ "$c" = xrange ] && a="XRANGE $k - +";;
          get|exists|del|hgetall|lrange|hkeys) a="$(echo $c | tr a-z A-Z) $k"; [ "$c" = lrange ] && a="LRANGE $k 0 1";;
          set) a="SET $k v";; expire) a="EXPIRE $k 10";; incr) a="INCR $k";; incrby) a="INCRBY $k 1";; hget|hdel) a="$(echo $c | tr a-z A-Z) $k f";;
          hset) a="HSET $k f v";; hincrby) a="HINCRBY $k f 1";; lpush|rpush) a="$(echo $c | tr a-z A-Z) $k v";; ltrim) a="LTRIM $k 0 1";;
          *) a="";;
        esac
        [ -n "$a" ] || continue
        out=$(admin_cli ACL DRYRUN "$u" $a 2>&1 | tr -d '\r'); [ "$out" = OK ] || { echo "FAIL $u: $a -> $out"; fail=1; }
      done
    done
    for a in "FLUSHALL" "KEYS *" "XADD zz.forbidden * e x" "GET zz:forbidden" "CONFIG GET maxmemory" "EVAL return 1 0"; do
      out=$(admin_cli ACL DRYRUN "$u" $a 2>&1 | tr -d '\r'); [ "$out" = OK ] && { echo "FAIL $u: '$a' lẽ ra bị chặn"; fail=1; }
    done
    echo "check $u: xong"
  done < <(svc_rules)
  [ "$fail" = 0 ] && echo "ACL check: OK" || { echo "ACL check: CÓ LỖI"; exit 1; }
  exit 0
fi
BAK="${BAK:-<SECRETS_DIR>-bak}"
if ! { [ -d "$BAK" ] && [ -w "$BAK" ]; } && ! mkdir -p "$BAK" 2>/dev/null; then BAK="$HOME/.tradingsys-secrets-bak"; fi
[ -w "$BAK" ] || BAK="$HOME/.tradingsys-secrets-bak"
mkdir -p "$BAK" && chmod 700 "$BAK"
SVC_VARS=$(svc_rules | cut -d'|' -f3 | tr '\n' ' ')
bak_done=0
for v in REDIS_ADMIN_PASSWORD REDIS_APP_PASSWORD REDIS_GATEWAY_PASSWORD REDIS_METRICS_PASSWORD REDIS_CACHE_PASSWORD REDIS_TRACKREC_PASSWORD $SVC_VARS; do
  if [ -z "$(envget $v)" ]; then
    [ "$bak_done" = 1 ] || { cp .env "$BAK/env-$(date +%s).bak"; chmod 600 "$BAK"/env-*.bak; bak_done=1; }
    printf '%s=%s\n' "$v" "$(openssl rand -hex 24)" >> .env; echo "đã thêm $v vào .env"
  fi
done
h() { printf '%s' "$(envget "$1")" | sha256sum | cut -d' ' -f1; }
if [ "$DEFAULT_OFF" = 1 ]; then DEF="user default off"; else DEF="user default on nopass ~* &* +@all"; fi
umask 022
cat > redis/users.acl.tmp <<ACL
$DEF
user ts_admin on #$(h REDIS_ADMIN_PASSWORD) ~* &* +@all
user ts_app on #$(h REDIS_APP_PASSWORD) ~* &* +@all -@dangerous -@admin -@scripting
user ts_gateway on #$(h REDIS_GATEWAY_PASSWORD) ~* &* -@all +@read +@connection
user ts_metrics on #$(h REDIS_METRICS_PASSWORD) ~* -@all +info +ping +client|list +client|setname +client|setinfo +config|get +slowlog|get +slowlog|len +latency|latest +latency|history +memory|usage +dbsize +scan +type +ttl +pttl +exists +xinfo +xlen +xpending +llen +hlen +scard +zcard +strlen +select +command|info +command|docs
user ts_cache on #$(h REDIS_CACHE_PASSWORD) resetkeys ~cache:* resetchannels -@all +get +set +mget +del +unlink +expire +pexpire +ttl +pttl +exists +incr +incrby +ping +hello +select +client|setname +client|setinfo
user ts_trackrec on #$(h REDIS_TRACKREC_PASSWORD) resetkeys ~tr:* resetchannels -@all +hset +hget +hgetall +hkeys +hlen +hdel +hmset +del +unlink +get +set +expire +exists +ttl +ping +hello +select +client|setname +client|setinfo
ACL
svc_rules | while IFS='|' read -r sv u v r; do
  echo "user $u on #$(h "$v") resetkeys resetchannels -@all +ping +hello +client|setinfo +client|setname $r" >> redis/users.acl.tmp
done
cat redis/users.acl.tmp > redis/users.acl; rm -f redis/users.acl.tmp; { chmod 644 redis/users.acl 2>/dev/null || true; }   # (file của root + ACL cc: chmod có thể bị từ chối, quyền hiện có đã đủ) ghi đè IN-PLACE (bind-mount file đơn: mv sẽ đổi inode)
echo "users.acl: default=$([ "$DEFAULT_OFF" = 1 ] && echo OFF || echo ON)"
# redis-cache (instance RIÊNG, chỉ-bộ-nhớ, allkeys-lru): ACL tối thiểu — default tắt, ts_admin (ops/healthcheck), ts_cache (gateway), ts_metrics.
cat > redis/users-cache.acl.tmp <<ACL
user default off
user ts_admin on #$(h REDIS_ADMIN_PASSWORD) ~* &* +@all
user ts_cache on #$(h REDIS_CACHE_PASSWORD) resetkeys ~cache:* resetchannels -@all +get +set +mget +del +unlink +expire +pexpire +ttl +pttl +exists +incr +incrby +ping +hello +select +client|setname +client|setinfo
user ts_metrics on #$(h REDIS_METRICS_PASSWORD) ~* -@all +info +ping +client|list +client|setname +client|setinfo +config|get +slowlog|get +slowlog|len +latency|latest +latency|history +memory|usage +dbsize +scan +type +ttl +pttl +exists +select +command|info +command|docs
ACL
cat redis/users-cache.acl.tmp > redis/users-cache.acl; rm -f redis/users-cache.acl.tmp; chmod 644 redis/users-cache.acl 2>/dev/null || true
echo "users-cache.acl: ok"
if [ "${1:-}" = "--load" ]; then
  out=$(admin_cli ACL LOAD 2>&1 | tr -d '\r'); echo "ACL LOAD (redis chính): $out"; [ "$out" = OK ] || exit 1
fi
