#!/usr/bin/env bash
# Diễn tập PITR: base backup mới nhất + WAL archive -> container tạm (không mạng, không publish) -> recovery tới cuối WAL -> kiểm tra truy vấn -> xoá.
# Dùng: pitr_restore_test.sh [RECOVERY_TARGET_TIME 'YYYY-MM-DD HH:MM:SS+00']  (mặc định: replay hết WAL). Chỉ động vào container/thư mục tạm riêng.
set -euo pipefail
INFRA="$(cd "$(dirname "$0")/.." && pwd)"; ROOT="$(dirname "$INFRA")"
KEY="${BACKUP_KEY:-/root/.tradingsys-backup.key}"; STATE="${STATE_DIR:-/var/lib/tradingsys-backup}"
IMG="${PG_IMAGE:-timescale/timescaledb:2.30.2-pg16}"
BASE="$(ls -1 "$ROOT"/backups/base/base-*.tar.gz.enc | sort | tail -1)"
W="$(mktemp -d /var/tmp/pitr-test.XXXXXX)"; N=tradingsys-pitrtest
cleanup() { docker rm -f "$N" >/dev/null 2>&1 || true; rm -rf "$W"; }; trap cleanup EXIT
mkdir -p "$W/data"; chmod 700 "$W/data"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "file:$KEY" -in "$BASE" | tar xzf - -C "$W/data"
touch "$W/data/recovery.signal"
{ echo "restore_command = 'gunzip -c /wal-archive/%f.gz > %p'"
  [ -n "${1:-}" ] && echo "recovery_target_time = '$1'" && echo "recovery_target_action = 'promote'" || echo "recovery_target = 'immediate'"
  echo "archive_mode = off"; } >> "$W/data/postgresql.auto.conf"
chown -R 70:70 "$W/data"
docker run -d --name "$N" --network none -v "$W/data:/var/lib/postgresql/data" -v "$ROOT/wal-archive:/wal-archive:ro" "$IMG" postgres -c archive_mode=off >/dev/null
for i in $(seq 1 60); do docker exec "$N" pg_isready -U ts -q 2>/dev/null && break; sleep 2; done
for i in $(seq 1 30); do [ "$(docker exec "$N" psql -U ts -d ts -Atc 'select pg_is_in_recovery()' 2>/dev/null)" = f ] && break; sleep 2; done
OUT=$(docker exec "$N" psql -U ts -d ts -Atc "select (select count(*) from bars)||' bars, '||(select count(*) from alerts)||' alerts, '||(select count(*) from news_items)||' news'")
echo "PITR OK: $OUT (base $(basename "$BASE"))"
date +%s > "$STATE/pitr_test.last_success"
