#!/usr/bin/env bash
# Áp 1 file migration SQL lên TimescaleDB bằng superuser ts (idempotent do từng file tự lo). Dùng:  sh infra/db/apply_migration.sh migrations/009_retention_compression.sql
# CALL/CREATE MATERIALIZED VIEW (continuous) KHÔNG chạy được trong transaction => KHÔNG dùng --single-transaction.
set -euo pipefail
cd "$(dirname "$0")/.."
F="${1:?cần đường dẫn file (tương đối infra/db hoặc tuyệt đối)}"
[ -f "db/$F" ] && F="db/$F"
envget() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
U="$(envget POSTGRES_USER)"; U="${U:-ts}"; DB="$(envget POSTGRES_DB)"; DB="${DB:-ts}"
docker compose -p tradingsys --env-file .env exec -T timescaledb psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 -f - < "$F"
echo "đã áp $F"
