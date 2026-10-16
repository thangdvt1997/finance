#!/usr/bin/env bash
# Tạo role ghi HẠN CHẾ `ts_trackrec` cho service track-record (idempotent) + áp migration 016_track_record.sql.
# Quyền: tr_views CHỈ SELECT/INSERT (+ trigger chặn UPDATE/DELETE/TRUNCATE); tr_entities/tr_outcomes/tr_scorecards/tr_runs đủ SELECT/INSERT/UPDATE/DELETE.
# KHÔNG đụng bảng nào khác (đọc dữ liệu thị trường/tin bằng ts_ro). Mật khẩu: POSTGRES_TRACKREC_PASSWORD trong infra/.env (chưa có thì sinh và THÊM vào .env).
set -euo pipefail
cd "$(dirname "$0")/.."
envget() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
U="$(envget POSTGRES_USER)"; U="${U:-ts}"; DB="$(envget POSTGRES_DB)"; DB="${DB:-ts}"
PW="$(envget POSTGRES_TRACKREC_PASSWORD)"
if [ -z "$PW" ]; then
  PW="$(openssl rand -hex 24)"
  mkdir -p <SECRETS_DIR>-bak; chmod 700 <SECRETS_DIR>-bak
  cp .env "<SECRETS_DIR>-bak/env-$(date +%s).bak"; chmod 600 <SECRETS_DIR>-bak/env-*.bak
  printf '\nPOSTGRES_TRACKREC_PASSWORD=%s\n' "$PW" >> .env
  echo "đã thêm POSTGRES_TRACKREC_PASSWORD vào .env"
fi
dc() { docker compose -p tradingsys --env-file .env -f docker-compose.yml exec -T timescaledb "$@"; }
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 < db/migrations/016_track_record.sql
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 -v pw="$PW" -v dbname="$DB" <<'SQL'
SELECT format('CREATE ROLE ts_trackrec LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', :'pw')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ts_trackrec') \gexec
ALTER ROLE ts_trackrec WITH PASSWORD :'pw';
ALTER ROLE ts_trackrec SET statement_timeout = '60s';
GRANT CONNECT ON DATABASE :"dbname" TO ts_trackrec;
GRANT USAGE ON SCHEMA public TO ts_trackrec;
REVOKE ALL ON tr_views FROM ts_trackrec;
GRANT SELECT, INSERT ON tr_views TO ts_trackrec;
GRANT SELECT, INSERT, UPDATE, DELETE ON tr_entities, tr_outcomes, tr_scorecards, tr_runs TO ts_trackrec;
GRANT USAGE, SELECT ON SEQUENCE tr_runs_id_seq TO ts_trackrec;
SQL
echo "ok: role ts_trackrec. TRACKREC_DB_RW_URL=postgresql://ts_trackrec:\${POSTGRES_TRACKREC_PASSWORD}@timescaledb:5432/$DB"
