#!/usr/bin/env bash
# Tạo role ghi HẠN CHẾ `ts_paper` cho service paper-trader (idempotent) + áp migration 003_paper.sql.
# Quyền: CONNECT; SELECT/INSERT/UPDATE trên paper_accounts, paper_orders, paper_positions; SELECT/INSERT trên paper_fills,
# paper_equity, paper_events, paper_chain, paper_config_versions (journal append-only). KHÔNG DDL, KHÔNG ghi bảng khác, KHÔNG DELETE.
# Chạy trên VPS: infra/db/create_paper_role.sh   (mật khẩu: POSTGRES_PAPER_PASSWORD trong infra/.env, chưa có thì sinh và THÊM vào .env)
set -euo pipefail
cd "$(dirname "$0")/.."
envget() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
U="$(envget POSTGRES_USER)"; U="${U:-ts}"; DB="$(envget POSTGRES_DB)"; DB="${DB:-ts}"
PW="$(envget POSTGRES_PAPER_PASSWORD)"
if [ -z "$PW" ]; then
  PW="$(openssl rand -hex 24)"
  cp .env ".env.bak.$(date +%s)"; chmod 600 .env.bak.*
  printf '\nPOSTGRES_PAPER_PASSWORD=%s\n' "$PW" >> .env
  echo "đã thêm POSTGRES_PAPER_PASSWORD vào .env"
fi
dc() { docker compose -p tradingsys --env-file .env -f docker-compose.yml exec -T timescaledb "$@"; }
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 < db/migrations/003_paper.sql
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 < db/migrations/004_paper_governance.sql   # hash-chain + phiên bản cấu hình (ts_paper: SELECT/INSERT)
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 -v pw="$PW" -v dbname="$DB" <<'SQL'
SELECT format('CREATE ROLE ts_paper LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', :'pw')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ts_paper') \gexec
ALTER ROLE ts_paper WITH PASSWORD :'pw';
ALTER ROLE ts_paper SET statement_timeout = '30s';
GRANT CONNECT ON DATABASE :"dbname" TO ts_paper;
GRANT USAGE ON SCHEMA public TO ts_paper;
GRANT SELECT, INSERT, UPDATE ON paper_accounts, paper_orders, paper_positions TO ts_paper;
GRANT SELECT, INSERT ON paper_fills, paper_equity, paper_events TO ts_paper;
GRANT SELECT, INSERT ON paper_chain, paper_config_versions TO ts_paper;
GRANT USAGE, SELECT ON SEQUENCE paper_fills_fill_id_seq, paper_events_id_seq TO ts_paper;
SQL
echo "ok: role ts_paper. PAPER_DB_RW_URL=postgresql://ts_paper:\${POSTGRES_PAPER_PASSWORD}@timescaledb:5432/$DB"
