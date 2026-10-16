#!/usr/bin/env bash
# Sinh infra/env/briefing.secrets (KEY=VALUE) từ infra/.env để briefing ĐỌC QUA FILE MOUNT :ro (BRIEFING_SECRETS_FILE),
# thay vì để DSN/mật khẩu nằm trong Config.Env (lộ qua `docker inspect`). Không in giá trị. Idempotent.
# File mode 644 nhưng nằm trong infra/env (thư mục 770 root/ACL) nên host khác không duyệt tới được; container uid 10001 đọc được qua bind mount.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "thiếu infra/.env" >&2; exit 1; }
g() { { grep -m1 "^$1=" .env || true; } | cut -d= -f2- | tr -d '\r' | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//"; }
req() { local v; v="$(g "$1")"; [ -n "$v" ] || { echo "thiếu $1 trong infra/.env" >&2; exit 1; }; printf '%s' "$v"; }
DB="$(g POSTGRES_DB)"; DB="${DB:-ts}"; RO="$(g POSTGRES_RO_USER)"; RO="${RO:-ts_ro}"
umask 022; tmp="env/.briefing.secrets.tmp"
{
  printf 'REDIS_URL=redis://ts_svc_briefing:%s@redis:6379/0\n' "$(req REDIS_SVC_BRIEFING_PASSWORD)"
  printf 'DATABASE_URL=postgresql://%s:%s@timescaledb:5432/%s\n' "$RO" "$(req POSTGRES_RO_PASSWORD)" "$DB"
  printf 'BRIEFING_DB_RW_URL=postgresql://ts_briefing:%s@timescaledb:5432/%s\n' "$(req POSTGRES_BRIEFING_PASSWORD)" "$DB"
  printf 'BRIEFING_ADMIN_TOKEN=%s\n' "$(g BRIEFING_ADMIN_TOKEN)"
} > "$tmp"
chmod 644 "$tmp"; mv -f "$tmp" env/briefing.secrets
echo "gen_briefing_secrets: ok (infra/env/briefing.secrets)"
