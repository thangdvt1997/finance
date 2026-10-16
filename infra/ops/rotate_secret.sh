#!/usr/bin/env bash
# Xoay bí mật dạng token ngẫu nhiên trong infra/.env — KHÔNG in giá trị (chỉ tên biến).
#   bash infra/ops/rotate_secret.sh API_TOKEN [BRIEFING_ADMIN_TOKEN ...]   sinh hex ngẫu nhiên (BYTES=24 -> 48 ký tự), ghi .env (0600, atomic)
#   bash infra/ops/rotate_secret.sh --prune-bak [N]                        giữ N bản sao lưu .env mới nhất (mặc định 2) trong <SECRETS_DIR>-bak, XOÁ infra/.env.bak.*
#   bash infra/ops/rotate_secret.sh --htpasswd-disable                      thay htpasswd (basic-auth dự phòng) bằng mật khẩu ngẫu nhiên KHÔNG ghi lại; muốn bật lại: services/web-ui/scripts/make-htpasswd.sh
# Chỉ cho phép biến trong ALLOW (token thuần). KHÔNG xoay ở đây: AUTH_SECRET_KEY/PUSH_ENC_KEY/VAPID_* (mất dữ liệu mã hoá/đăng ký), POSTGRES_*_PASSWORD (cần ALTER ROLE), REDIS_*_PASSWORD (cần redis_acl_render.sh).
# INTERNAL_TOKEN (X-Internal-Token): giá trị cũ chuyển sang INTERNAL_TOKEN_PREV (service vẫn chấp nhận) -> recreate service đích trước, api-gateway sau,
#   rồi xoá dòng INTERNAL_TOKEN_PREV + recreate lại service đích. INIT=1: tạo biến nếu .env chưa có (BYTES=32 khuyến nghị).
# Sau khi xoay: recreate MỌI service dùng biến đó cùng lúc (bảng SVC bên dưới in ra gợi ý), kiểm healthy, chạy e2e.
set -euo pipefail
cd "$(dirname "$0")/.."            # infra/
BAK="${BAK:-<SECRETS_DIR>-bak}"
# chạy bằng user không phải root (vd cc, không vào được thư mục root 700) -> sao lưu vào thư mục 700 của user đó
if ! { [ -d "$BAK" ] && [ -w "$BAK" ]; } && ! mkdir -p "$BAK" 2>/dev/null; then BAK="$HOME/.tradingsys-secrets-bak"; fi
[ -w "$BAK" ] || BAK="$HOME/.tradingsys-secrets-bak"
ALLOW=" API_TOKEN BRIEFING_ADMIN_TOKEN BACKFILL_TOKEN AUTH_TRUST_SECRET FLEET_INTERNAL_TOKEN BRIDGE_AUTH_TOKEN BRIDGE_ADMIN_TOKEN INTERNAL_TOKEN "
declare -A SVC=(
  [API_TOKEN]="api-gateway web-ui client-ui reporter paper-trader"
  [AUTH_TRUST_SECRET]="api-gateway web-ui client-ui auth"
  [FLEET_INTERNAL_TOKEN]="auth alert-rules reporter risk-monitor"
  [BRIDGE_AUTH_TOKEN]="auth mt-bridge"
  [BRIDGE_ADMIN_TOKEN]="mt-bridge"
  [BRIEFING_ADMIN_TOKEN]="briefing"
  [BACKFILL_TOKEN]="market-collector"
  [INTERNAL_TOKEN]="alert-rules journal risk-monitor paper-trader reporter briefing (TRƯỚC: nhận cả cũ qua INTERNAL_TOKEN_PREV) rồi api-gateway" )
prune() {
  local keep="${1:-2}"; mkdir -p "$BAK"; chmod 700 "$BAK"
  { ls -1 "$BAK"/env-*.bak 2>/dev/null || true; } | sort -r | tail -n +$((keep+1)) | xargs -r shred -u
  { ls -1 .env.bak.* 2>/dev/null || true; } | xargs -r shred -u
  echo "prune: còn $(ls -1 "$BAK"/env-*.bak 2>/dev/null | wc -l) bản sao lưu .env trong $BAK"
}
case "${1:-}" in
  --prune-bak) prune "${2:-2}"; exit 0;;
  --htpasswd-disable)
    f=web-ui/auth/htpasswd; u=$(cut -d: -f1 "$f" | head -1); u="${u:-admin}"
    umask 077; h=$(openssl passwd -apr1 "$(openssl rand -hex 24)")
    printf '%s:%s\n' "$u" "$h" > "$f.new"; chmod 644 "$f.new"; mv -f "$f.new" "$f"   # nginx worker đọc qua bind-mount ro => cần đọc được; hash apr1 của mật khẩu ngẫu nhiên đã bỏ
    echo "htpasswd: đã thay hash cho user '$u' bằng mật khẩu ngẫu nhiên không ghi lại (AUTH_BASIC_FALLBACK vẫn tắt)"; exit 0;;
  ''|-*) sed -n '2,8p' "$0"; exit 2;;
esac
mkdir -p "$BAK"; chmod 700 "$BAK"
cp .env "$BAK/env-$(date +%s).bak"; chmod 600 "$BAK"/env-*.bak
for k in "$@"; do
  case "$ALLOW" in *" $k "*) ;; *) echo "từ chối xoay '$k' (không nằm trong ALLOW)" >&2; exit 3;; esac
  if ! grep -q "^$k=" .env; then
    [ "${INIT:-0}" = 1 ] || { echo "$k không có trong .env (INIT=1 để tạo)" >&2; exit 4; }
    printf '%s=\n' "$k" >> .env
  fi
  v=$(openssl rand -hex "${BYTES:-24}")
  umask 077; tmp=$(mktemp .env.XXXXXX)
  prev=""; [ "$k" = INTERNAL_TOKEN ] && prev=INTERNAL_TOKEN_PREV
  awk -v k="$k" -v v="$v" -v p="$prev" 'BEGIN{FS=OFS="="}
    p!="" && $1==p {next}
    $1==k{ old=substr($0, length(k)+2); if (p!="" && old!="") print p"="old; print k"="v; next} {print}' .env > "$tmp"
  chmod 600 "$tmp"; { getfacl -p .env 2>/dev/null | setfacl --set-file=- "$tmp" 2>/dev/null; chmod o-rwx "$tmp"; } || true   # giữ ACL (user cc) của .env
  mv -f "$tmp" .env
  echo "đã xoay $k  -> recreate: ${SVC[$k]:-<tự xác định>}"
done
