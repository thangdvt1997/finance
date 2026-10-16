#!/usr/bin/env bash
# Tạo role ghi HẠN CHẾ `ts_pattern` cho service pattern-engine (idempotent) + áp migration 018_pattern_signals.sql.
# Quyền: CONNECT, SELECT/INSERT CHỈ trên pattern_signals (+ USAGE sequence id). KHÔNG UPDATE/DELETE, không DDL, không ghi bảng khác (nhật ký chỉ-thêm).
# Chạy trên VPS: infra/db/create_pattern_role.sh   (mật khẩu: POSTGRES_PATTERN_PASSWORD trong infra/.env, chưa có thì sinh và THÊM vào .env)
set -euo pipefail
cd "$(dirname "$0")/.."
envget() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
U="$(envget POSTGRES_USER)"; U="${U:-ts}"; DB="$(envget POSTGRES_DB)"; DB="${DB:-ts}"
PW="$(envget POSTGRES_PATTERN_PASSWORD)"
if [ -z "$PW" ]; then
  PW="$(openssl rand -hex 24)"
  cp .env ".env.bak.$(date +%s)"; chmod 600 .env.bak.*
  printf '\nPOSTGRES_PATTERN_PASSWORD=%s\n' "$PW" >> .env
  echo "đã thêm POSTGRES_PATTERN_PASSWORD vào .env"
fi
dc() { docker compose -p tradingsys --env-file .env -f docker-compose.yml exec -T timescaledb "$@"; }
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 < db/migrations/018_pattern_signals.sql
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 -v pw="$PW" -v dbname="$DB" <<'SQL'
SELECT format('CREATE ROLE ts_pattern LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', :'pw')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ts_pattern') \gexec
ALTER ROLE ts_pattern WITH PASSWORD :'pw';
ALTER ROLE ts_pattern SET statement_timeout = '30s';
GRANT CONNECT ON DATABASE :"dbname" TO ts_pattern;
GRANT USAGE ON SCHEMA public TO ts_pattern;
GRANT SELECT, INSERT ON pattern_signals TO ts_pattern;
GRANT USAGE, SELECT ON SEQUENCE pattern_signals_id_seq TO ts_pattern;
SQL
echo "ok: role ts_pattern. PATTERN_DB_RW_URL=postgresql://ts_pattern:\${POSTGRES_PATTERN_PASSWORD}@timescaledb:5432/$DB"
