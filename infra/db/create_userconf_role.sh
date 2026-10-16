#!/usr/bin/env bash
# Tạo role ghi HẠN CHẾ `ts_userconf` cho service alert-rules (idempotent) + áp migration 004_user_config.sql.
# Quyền: CONNECT; SELECT/INSERT/UPDATE/DELETE trên alert_rules, user_prefs; SELECT/INSERT/UPDATE trên alert_rule_events (UPDATE chỉ để ghi delivered).
# KHÔNG DDL, KHÔNG đụng bảng khác (không bars/quotes/account_*/paper_*).
# Chạy trên VPS: infra/db/create_userconf_role.sh   (mật khẩu: POSTGRES_USERCONF_PASSWORD trong infra/.env, chưa có thì sinh và THÊM vào .env)
set -euo pipefail
cd "$(dirname "$0")/.."
envget() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
U="$(envget POSTGRES_USER)"; U="${U:-ts}"; DB="$(envget POSTGRES_DB)"; DB="${DB:-ts}"
PW="$(envget POSTGRES_USERCONF_PASSWORD)"
if [ -z "$PW" ]; then
  PW="$(openssl rand -hex 24)"
  cp .env ".env.bak.$(date +%s)"; chmod 600 .env.bak.*
  printf '\nPOSTGRES_USERCONF_PASSWORD=%s\n' "$PW" >> .env
  echo "đã thêm POSTGRES_USERCONF_PASSWORD vào .env"
fi
dc() { docker compose -p tradingsys --env-file .env -f docker-compose.yml exec -T timescaledb "$@"; }
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 < db/migrations/004_user_config.sql
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 -v pw="$PW" -v dbname="$DB" <<'SQL'
SELECT format('CREATE ROLE ts_userconf LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', :'pw')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ts_userconf') \gexec
ALTER ROLE ts_userconf WITH PASSWORD :'pw';
ALTER ROLE ts_userconf SET statement_timeout = '30s';
GRANT CONNECT ON DATABASE :"dbname" TO ts_userconf;
GRANT USAGE ON SCHEMA public TO ts_userconf;
GRANT SELECT, INSERT, UPDATE, DELETE ON alert_rules, user_prefs TO ts_userconf;
GRANT SELECT, INSERT, UPDATE ON alert_rule_events TO ts_userconf;
GRANT USAGE, SELECT ON SEQUENCE alert_rule_events_id_seq TO ts_userconf;
SQL
echo "ok: role ts_userconf. USERCONF_DB_RW_URL=postgresql://ts_userconf:\${POSTGRES_USERCONF_PASSWORD}@timescaledb:5432/$DB"
