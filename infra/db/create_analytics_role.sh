#!/usr/bin/env bash
# Tạo role ghi HẠN CHẾ `ts_analytics` cho service analytics (idempotent) + áp migration 002_analytics.sql.
# Quyền: CONNECT, SELECT/INSERT/UPDATE/DELETE CHỈ trên analytics_snapshots. Không DDL, không ghi bảng khác.
# Chạy trên VPS: infra/db/create_analytics_role.sh   (mật khẩu: POSTGRES_ANALYTICS_PASSWORD trong infra/.env, chưa có thì sinh và THÊM vào .env)
set -euo pipefail
cd "$(dirname "$0")/.."
envget() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
U="$(envget POSTGRES_USER)"; U="${U:-ts}"; DB="$(envget POSTGRES_DB)"; DB="${DB:-ts}"
PW="$(envget POSTGRES_ANALYTICS_PASSWORD)"
if [ -z "$PW" ]; then
  PW="$(openssl rand -hex 24)"
  cp .env ".env.bak.$(date +%s)"; chmod 600 .env.bak.*
  printf '\nPOSTGRES_ANALYTICS_PASSWORD=%s\n' "$PW" >> .env
  echo "đã thêm POSTGRES_ANALYTICS_PASSWORD vào .env"
fi
dc() { docker compose -p tradingsys --env-file .env -f docker-compose.yml exec -T timescaledb "$@"; }
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 < db/migrations/002_analytics.sql
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 -v pw="$PW" -v dbname="$DB" <<'SQL'
SELECT format('CREATE ROLE ts_analytics LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', :'pw')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ts_analytics') \gexec
ALTER ROLE ts_analytics WITH PASSWORD :'pw';
ALTER ROLE ts_analytics SET statement_timeout = '30s';
GRANT CONNECT ON DATABASE :"dbname" TO ts_analytics;
GRANT USAGE ON SCHEMA public TO ts_analytics;
GRANT SELECT, INSERT, UPDATE, DELETE ON analytics_snapshots TO ts_analytics;
SQL
echo "ok: role ts_analytics. ANALYTICS_DB_RW_URL=postgresql://ts_analytics:\${POSTGRES_ANALYTICS_PASSWORD}@timescaledb:5432/$DB"
