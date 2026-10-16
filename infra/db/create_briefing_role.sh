#!/usr/bin/env bash
# Tạo role ghi HẠN CHẾ `ts_briefing` cho service briefing (idempotent) + áp migration 010_briefing.sql.
# Quyền: CONNECT; SELECT/INSERT CHỈ trên briefings. KHÔNG đụng bảng khác (đọc dữ liệu bằng ts_ro).
# Chạy trên VPS: infra/db/create_briefing_role.sh   (mật khẩu: POSTGRES_BRIEFING_PASSWORD trong infra/.env, chưa có thì sinh và THÊM vào .env)
set -euo pipefail
cd "$(dirname "$0")/.."
envget() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
U="$(envget POSTGRES_USER)"; U="${U:-ts}"; DB="$(envget POSTGRES_DB)"; DB="${DB:-ts}"
PW="$(envget POSTGRES_BRIEFING_PASSWORD)"
if [ -z "$PW" ]; then
  PW="$(openssl rand -hex 24)"
  mkdir -p <SECRETS_DIR>-bak; chmod 700 <SECRETS_DIR>-bak
  cp .env "<SECRETS_DIR>-bak/env-$(date +%s).bak"; chmod 600 <SECRETS_DIR>-bak/env-*.bak
  printf '\nPOSTGRES_BRIEFING_PASSWORD=%s\n' "$PW" >> .env
  echo "đã thêm POSTGRES_BRIEFING_PASSWORD vào .env"
fi
dc() { docker compose -p tradingsys --env-file .env -f docker-compose.yml exec -T timescaledb "$@"; }
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 < db/migrations/010_briefing.sql
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 -v pw="$PW" -v dbname="$DB" <<'SQL'
SELECT format('CREATE ROLE ts_briefing LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', :'pw')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ts_briefing') \gexec
ALTER ROLE ts_briefing WITH PASSWORD :'pw';
ALTER ROLE ts_briefing SET statement_timeout = '15s';
GRANT CONNECT ON DATABASE :"dbname" TO ts_briefing;
GRANT USAGE ON SCHEMA public TO ts_briefing;
GRANT SELECT, INSERT ON briefings TO ts_briefing;
SQL
echo "ok: role ts_briefing. BRIEFING_DB_RW_URL=postgresql://ts_briefing:\${POSTGRES_BRIEFING_PASSWORD}@timescaledb:5432/$DB"
