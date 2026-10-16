#!/usr/bin/env bash
# Tạo role ghi HẠN CHẾ `ts_dk` cho service data-keeper (idempotent) + schema `dk` (ts_dk sở hữu; chỉ tạo/ghi bảng trong dk.*).
# Quyền ghi hẹp: dk.* (toàn quyền) + INSERT-only trên bars (không UPDATE/DELETE); KHÔNG ghi quotes/account_*/paper_*.
# Quyền đọc public: SELECT bars/quotes (data-keeper đọc bằng ts_ro; ts_dk chỉ cần cho JOIN dk). Chạy trên VPS: infra/db/create_dk_role.sh
# Mật khẩu: POSTGRES_DK_PASSWORD trong infra/.env (chưa có thì sinh và THÊM vào .env).
set -euo pipefail
cd "$(dirname "$0")/.."
envget() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
U="$(envget POSTGRES_USER)"; U="${U:-ts}"; DB="$(envget POSTGRES_DB)"; DB="${DB:-ts}"
PW="$(envget POSTGRES_DK_PASSWORD)"
if [ -z "$PW" ]; then
  PW="$(openssl rand -hex 24)"
  cp .env ".env.bak.$(date +%s)"; chmod 600 .env.bak.*
  printf '\nPOSTGRES_DK_PASSWORD=%s\n' "$PW" >> .env
  echo "đã thêm POSTGRES_DK_PASSWORD vào .env"
fi
dc() { docker compose -p tradingsys --env-file .env -f docker-compose.yml exec -T timescaledb "$@"; }
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 -v pw="$PW" -v dbname="$DB" <<'SQL'
SELECT format('CREATE ROLE ts_dk LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', :'pw')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ts_dk') \gexec
ALTER ROLE ts_dk WITH PASSWORD :'pw';
ALTER ROLE ts_dk SET statement_timeout = '60s';
GRANT CONNECT ON DATABASE :"dbname" TO ts_dk;
CREATE SCHEMA IF NOT EXISTS dk AUTHORIZATION ts_dk;
GRANT USAGE ON SCHEMA public TO ts_dk;
GRANT SELECT ON bars, quotes TO ts_dk;   -- đọc (kiểm kê/gap/đối chiếu)
GRANT INSERT ON bars TO ts_dk;           -- backfill/histload: CHỈ INSERT (ON CONFLICT DO NOTHING); KHÔNG UPDATE/DELETE; mã chỉ ghi source canon:*
GRANT USAGE ON SCHEMA dk TO ts_ro;   -- api-gateway/UI đọc dk.* bằng role chỉ đọc
GRANT SELECT ON ALL TABLES IN SCHEMA dk TO ts_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE ts_dk IN SCHEMA dk GRANT SELECT ON TABLES TO ts_ro;
SQL
echo "ok: role ts_dk + schema dk. DK_DB_RW_URL=postgresql://ts_dk:\${POSTGRES_DK_PASSWORD}@timescaledb:5432/$DB"
