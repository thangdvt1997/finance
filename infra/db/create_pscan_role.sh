#!/usr/bin/env bash
# Tạo role hẹp `ts_pscan` cho service pattern-scan (idempotent) + áp migration 019_pattern_scan.sql.
# Quyền: SELECT/INSERT pattern_scan_events, pattern_scan_media, pattern_paper_ledger; SELECT/INSERT/UPDATE pattern_paper_trades
# (trigger chặn sửa lệnh đã đóng + thông số vào lệnh; ledger append-only). Không DELETE, không DDL, không bảng khác.
# Chạy: infra/db/create_pscan_role.sh  (mật khẩu POSTGRES_PSCAN_PASSWORD trong infra/.env, chưa có thì sinh và THÊM vào .env; không in ra)
set -euo pipefail
cd "$(dirname "$0")/.."
envget() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
U="$(envget POSTGRES_USER)"; U="${U:-ts}"; DB="$(envget POSTGRES_DB)"; DB="${DB:-ts}"
PW="$(envget POSTGRES_PSCAN_PASSWORD)"
if [ -z "$PW" ]; then
  PW="$(openssl rand -hex 24)"
  cp .env ".env.bak.$(date +%s)"; chmod 600 .env.bak.*
  printf '\nPOSTGRES_PSCAN_PASSWORD=%s\n' "$PW" >> .env
  echo "đã thêm POSTGRES_PSCAN_PASSWORD vào .env"
fi
dc() { docker exec -i tradingsys-timescaledb-1 "$@"; }
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 -q < db/migrations/019_pattern_scan.sql
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 -q -v pw="$PW" -v dbname="$DB" <<'SQL'
SELECT format('CREATE ROLE ts_pscan LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', :'pw')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ts_pscan') \gexec
ALTER ROLE ts_pscan WITH PASSWORD :'pw';
ALTER ROLE ts_pscan SET statement_timeout = '30s';
GRANT CONNECT ON DATABASE :"dbname" TO ts_pscan;
GRANT USAGE ON SCHEMA public TO ts_pscan;
GRANT SELECT, INSERT ON pattern_scan_events, pattern_scan_media, pattern_paper_ledger TO ts_pscan;
GRANT SELECT, INSERT, UPDATE ON pattern_paper_trades TO ts_pscan;
GRANT USAGE, SELECT ON SEQUENCE pattern_scan_events_id_seq, pattern_paper_trades_id_seq, pattern_paper_ledger_seq_seq TO ts_pscan;
SQL
echo "ok: role ts_pscan. PSCAN_DB_RW_URL=postgresql://ts_pscan:\${POSTGRES_PSCAN_PASSWORD}@timescaledb:5432/$DB"
