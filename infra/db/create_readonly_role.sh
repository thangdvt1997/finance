#!/usr/bin/env bash
# Tạo role chỉ-đọc `ts_ro` cho api-gateway (idempotent). Chạy trên VPS: infra/db/create_readonly_role.sh
# - Mật khẩu: lấy POSTGRES_RO_PASSWORD trong infra/.env; chưa có thì sinh ngẫu nhiên và THÊM vào .env (chmod 600 giữ nguyên).
# - Chỉ quyền SELECT trên mọi bảng hiện có + bảng tạo sau (do user ts), không DDL/ghi.
set -euo pipefail
cd "$(dirname "$0")/.."
envget() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
U="$(envget POSTGRES_USER)"; U="${U:-ts}"; DB="$(envget POSTGRES_DB)"; DB="${DB:-ts}"
PW="$(envget POSTGRES_RO_PASSWORD)"
if [ -z "$PW" ]; then
  PW="$(openssl rand -hex 24)"
  cp .env ".env.bak.$(date +%s)"; chmod 600 .env.bak.*
  printf '\nPOSTGRES_RO_PASSWORD=%s\n' "$PW" >> .env
  echo "đã thêm POSTGRES_RO_PASSWORD vào .env"
fi
dc() { docker compose -p tradingsys --env-file .env -f docker-compose.yml exec -T timescaledb "$@"; }
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 -v pw="$PW" -v dbname="$DB" -v owner="$U" <<'SQL'
SELECT format('CREATE ROLE ts_ro LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', :'pw')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ts_ro') \gexec
ALTER ROLE ts_ro WITH PASSWORD :'pw';
ALTER ROLE ts_ro SET default_transaction_read_only = on;
ALTER ROLE ts_ro SET statement_timeout = '15s';
GRANT CONNECT ON DATABASE :"dbname" TO ts_ro;
GRANT USAGE ON SCHEMA public TO ts_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ts_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public GRANT SELECT ON TABLES TO ts_ro;
SQL
echo "ok: role ts_ro (read-only). DATABASE_URL cho api-gateway: postgresql://ts_ro:\${POSTGRES_RO_PASSWORD}@timescaledb:5432/$DB"
