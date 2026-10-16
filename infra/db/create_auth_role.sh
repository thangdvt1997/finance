#!/usr/bin/env bash
# Tạo role ghi HẠN CHẾ `ts_auth` cho service auth (idempotent) + áp migration 011_auth.sql (+ role đọc hẹp `ts_mtauth` cho mt-bridge).
# ts_auth: SELECT/INSERT/UPDATE/DELETE CHỈ trên portal_users, mt_accounts, user_accounts, portal_sessions; audit_log CHỈ SELECT/INSERT (append-only).
# ts_mtauth (mt-bridge, tuỳ chọn): SELECT cột xác thực + UPDATE cột hạn chế trên mt_accounts — KHÔNG đụng portal_users/sessions.
# Chạy trên VPS: infra/db/create_auth_role.sh   (mật khẩu: POSTGRES_AUTH_PASSWORD / POSTGRES_MTAUTH_PASSWORD trong infra/.env, chưa có thì sinh và THÊM vào .env)
# Sinh thêm AUTH_SECRET_KEY (Fernet; KHÔNG đổi sau khi đã có dữ liệu mã hoá) và AUTH_TRUST_SECRET (nginx -> gateway) nếu chưa có.
set -euo pipefail
cd "$(dirname "$0")/.."
envget() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
U="$(envget POSTGRES_USER)"; U="${U:-ts}"; DB="$(envget POSTGRES_DB)"; DB="${DB:-ts}"
backup_env() { mkdir -p <SECRETS_DIR>-bak; chmod 700 <SECRETS_DIR>-bak; cp .env "<SECRETS_DIR>-bak/env-$(date +%s).bak"; chmod 600 <SECRETS_DIR>-bak/env-*.bak; }
ensure_var() {  # $1 = tên biến, $2 = lệnh sinh giá trị
  if [ -z "$(envget "$1")" ]; then backup_env; printf '\n%s=%s\n' "$1" "$(eval "$2")" >> .env; echo "đã thêm $1 vào .env" >&2; fi
}
ensure_var POSTGRES_AUTH_PASSWORD 'openssl rand -hex 24'
ensure_var POSTGRES_MTAUTH_PASSWORD 'openssl rand -hex 24'
ensure_var AUTH_SECRET_KEY "openssl rand -base64 32 | tr '+/' '-_'"
ensure_var AUTH_TRUST_SECRET 'openssl rand -hex 32'
ensure_var BRIDGE_AUTH_TOKEN 'openssl rand -hex 32'   # token dịch vụ 2 chiều auth<->mt-bridge (/internal/*)
PW="$(envget POSTGRES_AUTH_PASSWORD)"; PW2="$(envget POSTGRES_MTAUTH_PASSWORD)"
dc() { docker compose -p tradingsys --env-file .env -f docker-compose.yml exec -T timescaledb "$@"; }
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 < db/migrations/011_auth.sql
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 < db/migrations/012_auth_bridge.sql
dc psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 -v pw="$PW" -v pw2="$PW2" -v dbname="$DB" <<'SQL'
SELECT format('CREATE ROLE ts_auth LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', :'pw')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ts_auth') \gexec
ALTER ROLE ts_auth WITH PASSWORD :'pw';
ALTER ROLE ts_auth SET statement_timeout = '10s';
GRANT CONNECT ON DATABASE :"dbname" TO ts_auth;
GRANT USAGE ON SCHEMA public TO ts_auth;
GRANT SELECT, INSERT, UPDATE, DELETE ON portal_users, mt_accounts, user_accounts, portal_sessions TO ts_auth;
GRANT SELECT, INSERT ON audit_log TO ts_auth;
GRANT USAGE, SELECT ON SEQUENCE audit_log_id_seq TO ts_auth;
SELECT format('CREATE ROLE ts_mtauth LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', :'pw2')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ts_mtauth') \gexec
ALTER ROLE ts_mtauth WITH PASSWORD :'pw2';
ALTER ROLE ts_mtauth SET statement_timeout = '10s';
GRANT CONNECT ON DATABASE :"dbname" TO ts_mtauth;
GRANT USAGE ON SCHEMA public TO ts_mtauth;
REVOKE ALL ON mt_accounts FROM ts_mtauth;
GRANT SELECT (account_id, platform, login, server, label, client_id, status, ea_token_hash, ea_hmac_secret_enc, pairing_code_hash, pairing_expires_at, last_seen_at, created_at)
  ON mt_accounts TO ts_mtauth;
GRANT UPDATE (last_seen_at, ea_token_hash, pairing_code_hash, pairing_expires_at, status, server) ON mt_accounts TO ts_mtauth;
GRANT INSERT ON mt_accounts TO ts_mtauth;   -- EA tự khai báo lần đầu (status=pending, chưa có client)
-- ts_ro (gateway/journal/risk đọc DB) KHÔNG được thấy bảng auth (mặc định ts_ro có SELECT mọi bảng mới)
REVOKE ALL ON portal_users, mt_accounts, user_accounts, portal_sessions, audit_log FROM ts_ro;
SQL
echo "ok: role ts_auth, ts_mtauth. AUTH_DB_URL=postgresql://ts_auth:\${POSTGRES_AUTH_PASSWORD}@timescaledb:5432/$DB"
