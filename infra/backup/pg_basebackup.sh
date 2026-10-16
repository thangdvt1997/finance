#!/usr/bin/env bash
# Base backup vật lý (cho PITR cùng WAL archive /root/trading-system/wal-archive). Mã hoá cùng khoá. Chạy hằng tuần (tradingsys-basebackup.timer).
# Giữ 2 base mới nhất; WAL cũ hơn base CŨ NHẤT còn giữ bị xoá (cần cho PITR về mốc bất kỳ >= base cũ nhất).
set -euo pipefail
INFRA="$(cd "$(dirname "$0")/.." && pwd)"; ROOT="$(dirname "$INFRA")"
PROJ="${COMPOSE_PROJECT:-tradingsys}"; PG="${PG_CONTAINER:-${PROJ}-timescaledb-1}"
U="$({ grep -E '^POSTGRES_USER=' "$INFRA/.env" || true; } | head -1 | cut -d= -f2-)"; U="${U:-ts}"
OUT="${BACKUP_DIR:-$ROOT/backups}/base"; WAL="${WAL_DIR:-$ROOT/wal-archive}"; KEY="${BACKUP_KEY:-/root/.tradingsys-backup.key}"
STATE="${STATE_DIR:-/var/lib/tradingsys-backup}"; mkdir -p "$OUT" "$STATE"; chmod 700 "$OUT"
TS="$(date -u +%Y%m%dT%H%M%SZ)"; F="$OUT/base-$TS.tar.gz.enc"
fail() { echo "basebackup FAILED: $1" >&2; sh "$INFRA/ops/notify.sh" critical "Base backup Postgres THẤT BẠI" "$1"; exit 1; }
trap 'rm -f "$F.tmp"' EXIT
docker exec "$PG" pg_basebackup -U "$U" -D - -Ft -X fetch -Z 5 -c fast \
  | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass "file:$KEY" -out "$F.tmp" || fail "pg_basebackup lỗi"
[ -s "$F.tmp" ] || fail "rỗng"
mv "$F.tmp" "$F"; chmod 600 "$F"; date +%s > "$STATE/basebackup.last_success"; echo "$F" > "$STATE/basebackup.last_file"
# retention: giữ 2 base; xoá WAL cũ hơn base cũ nhất còn giữ
ls -1t "$OUT"/base-*.tar.gz.enc | tail -n +3 | xargs -r rm -f --
OLDEST="$(ls -1tr "$OUT"/base-*.tar.gz.enc | head -1)"
[ -d "$WAL" ] && find "$WAL" -name '*.gz' ! -newer "$OLDEST" -mmin +60 -delete 2>/dev/null || true
echo "basebackup ok: $F ($(du -h "$F" | cut -f1)); WAL archive: $(ls -1 "$WAL" 2>/dev/null | wc -l) file, $(du -sh "$WAL" 2>/dev/null | cut -f1)"
