#!/usr/bin/env bash
# Tạo role ghi HẠN CHẾ `ts_vn` cho service vn-market (idempotent) + áp migration 005_vn_market.sql.
# Quyền: SELECT/INSERT/UPDATE/DELETE trên vn_*; SELECT trên news_items (tin theo mã). KHÔNG DDL, KHÔNG đụng bảng khác (bars/quotes/account_*/paper_*).
# Chạy trên VPS: infra/db/create_vn_role.sh   (mật khẩu: POSTGRES_VN_PASSWORD trong infra/.env, chưa có thì sinh và THÊM vào .env)
set -euo pipefail
cd "$(dirname "$0")/.."
envget() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
U="$(envget POSTGRES_USER)"; U="${U:-ts}"; DB="$(envget POSTGRES_DB)"; DB="${DB:-ts}"
PW="$(envget POSTGRES_VN_PASSWORD)"
if [ -z "$PW" ]; then
  PW="$(openssl rand -hex 24)"
  cp .env ".env.bak.$(date +%s)"; chmod 600 .env.bak.*
  printf '\nPOSTGRES_VN_PASSWORD=%s\n' "$PW" >> .env
  echo "đã thêm POSTGRES_VN_PASSWORD vào .env"
fi
dc() { docker compose -p tradingsys --env-file .env -f docker-compose.yml exec -T timescaledb "$@"; }
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 < db/migrations/005_vn_market.sql
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 -v pw="$PW" -v dbname="$DB" <<'SQL'
SELECT format('CREATE ROLE ts_vn LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', :'pw')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ts_vn') \gexec
ALTER ROLE ts_vn WITH PASSWORD :'pw';
ALTER ROLE ts_vn SET statement_timeout = '30s';
GRANT CONNECT ON DATABASE :"dbname" TO ts_vn;
GRANT USAGE ON SCHEMA public TO ts_vn;
GRANT SELECT, INSERT, UPDATE, DELETE ON vn_symbols, vn_daily, vn_index_daily, vn_foreign, vn_ratios, vn_events, vn_meta TO ts_vn;
GRANT SELECT ON news_items TO ts_vn;
SQL
echo "ok: role ts_vn. VN_DB_URL=postgresql://ts_vn:\${POSTGRES_VN_PASSWORD}@timescaledb:5432/$DB"
