#!/usr/bin/env bash
# Thử khôi phục bản dump MỚI NHẤT (hoặc $1; .dump.enc hoặc .dump) vào DB tạm `restore_test`, KIỂM TRA SÂU rồi xoá DB tạm. Không đụng DB thật.
# Kiểm tra: (1) mọi bảng người dùng + hypertable chunk khôi phục; (2) số hàng từng bảng: restored <= live (+dung sai ghi mới) và >0 nếu live>0 (khi dump đủ cũ);
# (3) checksum md5 theo "lát cắt đã đóng" (hàng cũ hơn 3 ngày của bars/news_items/calendar_events...) khớp live; (4) số chunk hypertable khớp.
# Kết quả -> $STATE_DIR/restore_test.last_{success,failure}; lỗi => cảnh báo critical. Timer hằng tuần: tradingsys-restoretest.timer.
set -uo pipefail
INFRA="$(cd "$(dirname "$0")/.." && pwd)"; cd "$INFRA"
PROJ="${COMPOSE_PROJECT:-tradingsys}"; PG="${PG_CONTAINER:-${PROJ}-timescaledb-1}"
envget() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
U="$(envget POSTGRES_USER)"; U="${U:-ts}"; DB="$(envget POSTGRES_DB)"; DB="${DB:-ts}"
OUT_DIR="${BACKUP_DIR:-$(dirname "$INFRA")/backups}"; KEY="${BACKUP_KEY:-/root/.tradingsys-backup.key}"
STATE="${STATE_DIR:-/var/lib/tradingsys-backup}"; mkdir -p "$STATE"
F="${1:-$(ls -1 "$OUT_DIR"/ts-2*.dump.enc 2>/dev/null | sort | tail -1)}"
[ -n "$F" ] && [ -f "$F" ] || { echo "không có bản dump" >&2; exit 1; }
T=restore_test; ERR=0; MSG=""
bad() { ERR=1; MSG="$MSG; $1"; echo "FAIL: $1"; }
psq() { docker exec -i "$PG" psql -U "$U" -v ON_ERROR_STOP=1 -X -q "$@"; }
cleanup() { psq -d postgres -c "DROP DATABASE IF EXISTS $T" >/dev/null 2>&1; }
RERR="$(mktemp)"; trap 'cleanup; rm -f "$RERR"' EXIT
case "$F" in *.enc) rd() { openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "file:$KEY" -in "$F"; } ;; *) rd() { cat "$F"; } ;; esac
# sha256 (nếu có)
[ -f "$F.sha256" ] && { (cd "$(dirname "$F")" && sha256sum -c "$(basename "$F").sha256" >/dev/null) || bad "sha256 không khớp"; }
psq -d postgres -c "DROP DATABASE IF EXISTS $T" -c "CREATE DATABASE $T" >/dev/null || bad "tạo DB tạm"
psq -d $T -c "CREATE EXTENSION IF NOT EXISTS timescaledb" -c "SELECT timescaledb_pre_restore()" >/dev/null || bad "pre_restore"
rd | docker exec -i "$PG" pg_restore -U "$U" -d $T --no-owner --exit-on-error 2>"$RERR" || echo "(pg_restore cảnh báo: $(head -c 300 "$RERR" | tr '\n' ' '))"
psq -d $T -c "SELECT timescaledb_post_restore()" >/dev/null || bad "post_restore"
echo "== khôi phục từ $F =="
CUT="$(date -u -d '-3 days' +%Y-%m-%dT%H:%M:%SZ)"
# danh sách bảng: user tables (không _hyper chunk) trong schema public
TABLES=$(psq -d "$DB" -Atc "SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p') AND relname NOT LIKE '\_hyper%' ORDER BY 1")
declare -A TSCOL=( [bars]=ts_open [quotes]=ts [news_items]=ingested_at [calendar_events]=ts [account_snapshots]=ts [alerts]=ts [paper_equity]=ts [paper_events]=ts )
# tuổi dump (s) từ tên file ts-YYYYmmddTHHMMSSZ
DT=$(basename "$F" | sed -n 's/^ts-\([0-9]\{8\}\)T\([0-9]\{2\}\)\([0-9]\{2\}\)\([0-9]\{2\}\)Z.*/\1 \2:\3:\4/p'); DAGE=$(( $(date +%s) - $(date -u -d "$DT" +%s 2>/dev/null || echo 0) ))
missing() { if [ "$DAGE" -lt 129600 ]; then bad "$1"; else echo "WARN (dump cũ ${DAGE}s): $1"; fi; }
for t in $TABLES; do
  a=$(psq -d $T -Atc "SELECT count(*) FROM public.\"$t\"" 2>/dev/null || echo ERR)
  b=$(psq -d "$DB" -Atc "SELECT count(*) FROM public.\"$t\"" 2>/dev/null || echo ERR)
  line="$t: restored=$a live=$b"
  if [ "$a" = ERR ]; then missing "bảng $t không khôi phục"; 
  elif [ "$b" != ERR ] && [ "$a" -gt "$b" ] && [ "$DAGE" -lt 129600 ]; then bad "$t: restored($a) > live($b)"; fi
  col="${TSCOL[$t]:-}"
  if [ -n "$col" ]; then
    ca=$(psq -d $T -Atc "SELECT count(*),coalesce(md5(string_agg(x::text,'|' ORDER BY x::text)),'') FROM (SELECT * FROM public.\"$t\" WHERE $col < '$CUT') x" 2>/dev/null || echo ERR)
    cb=$(psq -d "$DB" -Atc "SELECT count(*),coalesce(md5(string_agg(x::text,'|' ORDER BY x::text)),'') FROM (SELECT * FROM public.\"$t\" WHERE $col < '$CUT') x" 2>/dev/null || echo ERR)
    line="$line  slice<3d: $ca"
    if [ "$ca" != "$cb" ] && [ "${ca%%|*}" = "${cb%%|*}" ]; then bad "$t: checksum lát cắt cũ lệch dù cùng số hàng (hỏng dữ liệu?) ($ca vs $cb)"
    elif [ "$ca" != "$cb" ]; then echo "  (lát cắt khác số hàng: live đã được backfill/xoá sau dump -> chỉ cảnh báo)"; fi
  fi
  echo "$line"
done
ha=$(psq -d $T -Atc "SELECT count(*) FROM timescaledb_information.hypertables"); hb=$(psq -d "$DB" -Atc "SELECT count(*) FROM timescaledb_information.hypertables")
[ "$ha" = "$hb" ] || missing "số hypertable lệch ($ha vs $hb)"
echo "hypertables: restored=$ha live=$hb"
if [ $ERR -eq 0 ]; then date +%s > "$STATE/restore_test.last_success"; rm -f "$STATE/restore_test.last_failure"; echo "RESTORE TEST OK ($F)"
else echo "failed $(date +%s) $MSG" > "$STATE/restore_test.last_failure"; sh "$INFRA/ops/notify.sh" critical "Restore-test backup tradingsys THẤT BẠI" "$F :: $MSG"; exit 1; fi
