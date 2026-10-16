#!/usr/bin/env bash
# Tạo role giám sát `ts_monitor` cho postgres-exporter (idempotent): thành viên pg_monitor (đọc pg_stat_*), SELECT chỉ các bảng/cagg dùng cho metric độ tươi. Không ghi, không DDL.
# Mật khẩu POSTGRES_MONITOR_PASSWORD: sinh ngẫu nhiên và thêm vào infra/.env nếu chưa có. Chạy trên VPS: bash infra/db/create_monitor_role.sh
set -euo pipefail
cd "$(dirname "$0")/.."
envget() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
U="$(envget POSTGRES_USER)"; U="${U:-ts}"; DB="$(envget POSTGRES_DB)"; DB="${DB:-ts}"
PW="$(envget POSTGRES_MONITOR_PASSWORD)"
if [ -z "$PW" ]; then
  PW="$(openssl rand -hex 24)"
  mkdir -p <SECRETS_DIR>-bak && chmod 700 <SECRETS_DIR>-bak
  cp .env "<SECRETS_DIR>-bak/env-$(date +%s).bak"; chmod 600 <SECRETS_DIR>-bak/env-*.bak
  printf '\nPOSTGRES_MONITOR_PASSWORD=%s\n' "$PW" >> .env
  echo "đã thêm POSTGRES_MONITOR_PASSWORD vào .env"
fi
docker compose -p tradingsys --env-file .env exec -T timescaledb psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 -v pw="$PW" -v dbname="$DB" <<'SQL'
SELECT format('CREATE ROLE ts_monitor LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', :'pw')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ts_monitor') \gexec
ALTER ROLE ts_monitor WITH PASSWORD :'pw';
ALTER ROLE ts_monitor SET default_transaction_read_only = on;
ALTER ROLE ts_monitor SET statement_timeout = '10s';
ALTER ROLE ts_monitor CONNECTION LIMIT 5;
GRANT pg_monitor TO ts_monitor;
GRANT CONNECT ON DATABASE :"dbname" TO ts_monitor;
GRANT USAGE ON SCHEMA public TO ts_monitor;
DO $$ BEGIN
  IF to_regclass('public.bars_daily_stats') IS NOT NULL THEN GRANT SELECT ON bars_daily_stats TO ts_monitor; END IF;
  IF to_regclass('public.bars') IS NOT NULL THEN GRANT SELECT ON bars TO ts_monitor; END IF;
  IF to_regclass('public.quotes') IS NOT NULL THEN GRANT SELECT ON quotes TO ts_monitor; END IF;
  IF to_regclass('public.news_items') IS NOT NULL THEN GRANT SELECT ON news_items TO ts_monitor; END IF;
  IF to_regclass('public.alerts') IS NOT NULL THEN GRANT SELECT ON alerts TO ts_monitor; END IF;
END $$;
SQL
echo "ok: role ts_monitor (pg_monitor + SELECT độ tươi)"
