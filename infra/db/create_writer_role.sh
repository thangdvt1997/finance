#!/usr/bin/env bash
# Tạo role ghi HẠN CHẾ `ts_writer` cho storage-writer (idempotent): SELECT/INSERT/UPDATE đúng 9 bảng dữ liệu + account_deals; KHÔNG DELETE/TRUNCATE/DDL/superuser.
# Superuser `ts` chỉ còn dùng cho migration/backup. Mật khẩu: POSTGRES_WRITER_PASSWORD trong infra/.env (chưa có thì sinh + THÊM vào .env, sao lưu .env vào <SECRETS_DIR>-bak).
set -euo pipefail
cd "$(dirname "$0")/.."
envget() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
U="$(envget POSTGRES_USER)"; U="${U:-ts}"; DB="$(envget POSTGRES_DB)"; DB="${DB:-ts}"
PW="$(envget POSTGRES_WRITER_PASSWORD)"
if [ -z "$PW" ]; then
  PW="$(openssl rand -hex 24)"
  mkdir -p <SECRETS_DIR>-bak; chmod 700 <SECRETS_DIR>-bak
  cp .env "<SECRETS_DIR>-bak/env-$(date +%s).bak"; chmod 600 <SECRETS_DIR>-bak/env-*.bak
  printf '\nPOSTGRES_WRITER_PASSWORD=%s\n' "$PW" >> .env
  echo "đã thêm POSTGRES_WRITER_PASSWORD vào .env"
fi
docker exec -i "${COMPOSE_PROJECT:-tradingsys}-timescaledb-1" psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 -v pw="$PW" -v dbname="$DB" -v owner="$U" <<'SQL'
SELECT format('CREATE ROLE ts_writer LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION', :'pw')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ts_writer') \gexec
ALTER ROLE ts_writer WITH PASSWORD :'pw';
ALTER ROLE ts_writer SET statement_timeout = '30s';
GRANT CONNECT ON DATABASE :"dbname" TO ts_writer;
GRANT USAGE ON SCHEMA public TO ts_writer;
GRANT SELECT, INSERT, UPDATE ON bars, quotes, news_items, calendar_events, experts, expert_signals, expert_positions, account_snapshots, alerts TO ts_writer;
-- account_deals (migration 005_journal): lich su deal da dong tu account.deals
DO $$ BEGIN IF to_regclass('public.account_deals') IS NOT NULL THEN GRANT SELECT, INSERT, UPDATE ON account_deals TO ts_writer; END IF; END $$;
-- account_orders (migration 013_client_backend): lenh cho theo tai khoan tu account.snapshots
DO $$ BEGIN IF to_regclass('public.account_orders') IS NOT NULL THEN GRANT SELECT, INSERT, UPDATE ON account_orders TO ts_writer; END IF; END $$;
-- bảng có cột serial/identity (alerts.id...): cần USAGE trên sequence của đúng các bảng trên
DO $$ DECLARE s record; BEGIN
  FOR s IN SELECT format('%I.%I', n.nspname, c.relname) AS q FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           JOIN pg_depend d ON d.objid=c.oid AND d.deptype IN ('a','i') JOIN pg_class t ON t.oid=d.refobjid
           WHERE c.relkind='S' AND n.nspname='public' AND t.relname IN ('bars','quotes','news_items','calendar_events','experts','expert_signals','expert_positions','account_snapshots','alerts','account_deals')
  LOOP EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO ts_writer', s.q); END LOOP; END $$;
-- cột mở rộng news_enrichment (migration 002_news_enrichment) nằm trong news_items => đã nằm trong GRANT bảng.
SQL
echo "ok: role ts_writer. DATABASE_URL của storage-writer: postgresql://ts_writer:\${POSTGRES_WRITER_PASSWORD}@timescaledb:5432/$DB"
