#!/usr/bin/env bash
# Backup TimescaleDB: pg_dump -Fc -> MÃ HOÁ (openssl aes-256-cbc/pbkdf2, khoá /root/.tradingsys-backup.key) -> xác minh (giải mã + pg_restore -l)
# -> sha256 -> gói cấu hình (.env, htpasswd, accounts.yaml) cũng mã hoá -> đẩy off-site nếu cấu hình (backup/offsite.sh) -> dọn bản cũ.
# Chạy bởi systemd timer tradingsys-backup.timer (03:10 UTC). Thất bại => cảnh báo critical qua alert-service.
# Biến: BACKUP_DIR (<repo>/backups), KEEP (14), COMPOSE_PROJECT (tradingsys), BACKUP_KEY (/root/.tradingsys-backup.key), STATE_DIR (/var/lib/tradingsys-backup)
set -euo pipefail
INFRA="$(cd "$(dirname "$0")/.." && pwd)"
cd "$INFRA"
PROJ="${COMPOSE_PROJECT:-tradingsys}"
PG="${PG_CONTAINER:-${PROJ}-timescaledb-1}"
# Không `source` .env (có giá trị chứa dấu ngoặc); chỉ lấy biến cần.
envget() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
POSTGRES_USER="$(envget POSTGRES_USER)"; POSTGRES_USER="${POSTGRES_USER:-ts}"
POSTGRES_DB="$(envget POSTGRES_DB)"; POSTGRES_DB="${POSTGRES_DB:-ts}"
OUT_DIR="${BACKUP_DIR:-$(dirname "$INFRA")/backups}"
KEEP="${KEEP:-14}"
KEY="${BACKUP_KEY:-/root/.tradingsys-backup.key}"
STATE="${STATE_DIR:-/var/lib/tradingsys-backup}"
mkdir -p "$OUT_DIR" "$STATE"; chmod 700 "$OUT_DIR" "$STATE"
if [ ! -s "$KEY" ]; then umask 077; openssl rand -base64 48 > "$KEY"; echo "ĐÃ SINH khoá backup mới $KEY — HÃY SAO CHÉP RA NGOÀI VPS (xem docs/DR_RUNBOOK.md)" >&2; fi
chmod 600 "$KEY"
ENC=(openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass "file:$KEY")
DEC=(openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "file:$KEY")
TS="$(date -u +%Y%m%dT%H%M%SZ)"
F="$OUT_DIR/ts-$TS.dump.enc"
fail() { echo "backup FAILED: $1" >&2; echo "failed $(date +%s) $1" > "$STATE/backup.last_failure"; sh "$INFRA/ops/notify.sh" critical "Backup tradingsys THẤT BẠI" "$1" || true; exit 1; }
trap 'rm -f "$F.tmp" "$OUT_DIR"/config-*.tmp' EXIT
docker exec "$PG" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc | "${ENC[@]}" -out "$F.tmp" || fail "pg_dump|encrypt lỗi"
[ -s "$F.tmp" ] || fail "dump rỗng"
# xác minh bản ĐÃ MÃ HOÁ giải mã được và TOC đọc được
TOC=$(set +o pipefail; "${DEC[@]}" -in "$F.tmp" 2>/dev/null | docker exec -i "$PG" pg_restore -l 2>/dev/null | wc -l)  # pg_restore -l đóng stdin sớm => tắt pipefail
[ "${TOC:-0}" -gt 20 ] || fail "xác minh (giải mã + pg_restore -l) lỗi: TOC=$TOC dòng"
mv "$F.tmp" "$F"; chmod 600 "$F"
(cd "$OUT_DIR" && sha256sum "$(basename "$F")" > "$F.sha256")
# gói cấu hình/secret (mã hoá): .env, htpasswd, accounts.yaml
CF="$OUT_DIR/ts-config-$TS.tar.gz.enc"
tar czf - -C "$(dirname "$INFRA")" infra/.env infra/web-ui/auth infra/mt-bridge 2>/dev/null | "${ENC[@]}" -out "$CF" && chmod 600 "$CF" || echo "cảnh báo: gói cấu hình lỗi" >&2
# bản sao theo thời gian (giữ cả bản cũ dạng chưa mã hoá do phiên bản trước: mã hoá rồi xoá)
for old in "$OUT_DIR"/ts-*.dump; do [ -e "$old" ] || continue; "${ENC[@]}" -in "$old" -out "$old.enc" && rm -f "$old"; done
date +%s > "$STATE/backup.last_success"; echo "$F" > "$STATE/backup.last_file"; rm -f "$STATE/backup.last_failure"
# off-site (không bắt buộc; lỗi off-site => cảnh báo nhưng dump local vẫn hợp lệ)
[ -x "$INFRA/backup/offsite.sh" ] && { "$INFRA/backup/offsite.sh" "$OUT_DIR" || sh "$INFRA/ops/notify.sh" warning "Backup off-site lỗi" "offsite.sh trả lỗi; dump local $F vẫn hợp lệ"; }
# giữ KEEP bản mới nhất
ls -1t "$OUT_DIR"/ts-2*.dump.enc | tail -n +"$((KEEP + 1))" | while read -r x; do rm -f -- "$x" "$x.sha256"; done
ls -1t "$OUT_DIR"/ts-config-*.tar.gz.enc | tail -n +"$((KEEP + 1))" | xargs -r rm -f --
echo "backup ok: $F ($(du -h "$F" | cut -f1)); còn $(ls -1 "$OUT_DIR"/ts-2*.dump.enc | wc -l) bản mã hoá"
