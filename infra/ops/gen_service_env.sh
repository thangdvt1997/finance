#!/usr/bin/env bash
# Sinh infra/env/<service>.env từ infra/.env theo allowlist infra/ops/service_env.manifest (ARCH_AUDIT S-5: tách secrets theo service).
# Dùng:  sh infra/ops/gen_service_env.sh [--report]     (deploy.sh tự gọi trước `docker compose up`)
#   --report : liệt kê biến .env không service nào nhận (chỉ dùng cho nội suy compose: mật khẩu DB, BIND/PORT...) và biến manifest không khớp gì.
# Không in giá trị. File đầu ra chmod 600. Bash thuần, idempotent.
set -euo pipefail
cd "$(dirname "$0")/.."
MAN=ops/service_env.manifest; OUT=env
[ -f .env ] || { echo "thiếu infra/.env" >&2; exit 1; }
mkdir -p "$OUT"; chmod 700 "$OUT" 2>/dev/null || [ -w "$OUT" ]   # dir thuộc root khi chạy bằng user cc (ACL): bỏ qua chmod
declare -A PATS
while IFS= read -r line; do
  line="${line%$'\r'}"   # manifest có thể có CRLF (checkout Windows): bỏ CR để mẫu cuối dòng khớp
  case "$line" in ''|'#'*) continue;; esac
  svc="${line%%:*}"; pats="${line#*:}"; PATS["$svc"]="$pats"
done < "$MAN"
declare -A USED
set -f   # tắt glob khi tách pattern
for svc in "${!PATS[@]}"; do
  tmp="$OUT/.$svc.env.tmp"; : > "$tmp"
  while IFS= read -r l || [ -n "$l" ]; do
    case "$l" in ''|'#'*) continue;; esac
    k="${l%%=*}"
    case "$k" in *[!A-Za-z0-9_]*|'') continue;; esac
    for p in ${PATS[$svc]}; do
      # shellcheck disable=SC2254
      case "$k" in $p) printf '%s\n' "$l" >> "$tmp"; USED["$k"]=1; break;; esac
    done
  done < .env
  chmod 600 "$tmp"; mv "$tmp" "$OUT/$svc.env"
done
set +f
echo "gen_service_env: $(ls "$OUT"/*.env | wc -l) file trong infra/$OUT/"
if [ "${1:-}" = "--report" ]; then
  echo "--- biến .env KHÔNG service nào nhận (chỉ nội suy compose):"
  while IFS= read -r l || [ -n "$l" ]; do
    case "$l" in ''|'#'*) continue;; esac; k="${l%%=*}"
    case "$k" in *[!A-Za-z0-9_]*|'') continue;; esac
    [ -n "${USED[$k]:-}" ] || echo "  $k"
  done < .env | sort -u
fi
