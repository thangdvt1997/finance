#!/usr/bin/env bash
# Tạo role ghi HẠN CHẾ `ts_journal` cho service journal (idempotent) + áp migration 005_journal.sql.
# Quyền: CONNECT; SELECT/INSERT/UPDATE/DELETE CHỈ trên journal_notes. KHÔNG đụng account_deals/paper_*/bars/... (đọc dữ liệu bằng ts_ro).
# Chạy trên VPS: infra/db/create_journal_role.sh   (mật khẩu: POSTGRES_JOURNAL_PASSWORD trong infra/.env, chưa có thì sinh và THÊM vào .env)
set -euo pipefail
cd "$(dirname "$0")/.."
envget() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
U="$(envget POSTGRES_USER)"; U="${U:-ts}"; DB="$(envget POSTGRES_DB)"; DB="${DB:-ts}"
PW="$(envget POSTGRES_JOURNAL_PASSWORD)"
if [ -z "$PW" ]; then
  PW="$(openssl rand -hex 24)"
  mkdir -p <SECRETS_DIR>-bak; chmod 700 <SECRETS_DIR>-bak
  cp .env "<SECRETS_DIR>-bak/env-$(date +%s).bak"; chmod 600 <SECRETS_DIR>-bak/env-*.bak
  printf '\nPOSTGRES_JOURNAL_PASSWORD=%s\n' "$PW" >> .env
  echo "đã thêm POSTGRES_JOURNAL_PASSWORD vào .env"
fi
dc() { docker compose -p tradingsys --env-file .env -f docker-compose.yml exec -T timescaledb "$@"; }
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 < db/migrations/005_journal.sql
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 -v pw="$PW" -v dbname="$DB" <<'SQL'
SELECT format('CREATE ROLE ts_journal LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', :'pw')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ts_journal') \gexec
ALTER ROLE ts_journal WITH PASSWORD :'pw';
ALTER ROLE ts_journal SET statement_timeout = '15s';
GRANT CONNECT ON DATABASE :"dbname" TO ts_journal;
GRANT USAGE ON SCHEMA public TO ts_journal;
GRANT SELECT, INSERT, UPDATE, DELETE ON journal_notes TO ts_journal;
SQL
echo "ok: role ts_journal. JOURNAL_DB_RW_URL=postgresql://ts_journal:\${POSTGRES_JOURNAL_PASSWORD}@timescaledb:5432/$DB"
