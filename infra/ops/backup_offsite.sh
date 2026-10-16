#!/usr/bin/env bash
# Đẩy backup MÃ HOÁ ra ngoài VPS (rclone hoặc rsync/ssh), có kiểm checksum, giữ N bản, log, timeout.
# MẶC ĐỊNH DRY-RUN: chỉ in việc sẽ làm. Chạy thật khi: OFFSITE_APPLY=1 (hoặc --apply) VÀ đã cấu hình đích.
# Cấu hình qua biến môi trường hoặc file infra/ops/backup_offsite.env (chmod 600, KHÔNG commit):
#   OFFSITE_MODE=rclone|rsync          (mặc định rclone)
#   OFFSITE_DEST=remote:bucket/path    (rclone)  |  user@host:/duong/dan  (rsync/ssh)
#   RCLONE_CONFIG=/root/.config/tradingsys-rclone.conf   OFFSITE_SSH_KEY=/root/.ssh/tradingsys_offsite (rsync)
#   OFFSITE_KEEP=14   OFFSITE_TIMEOUT=900 (giây)   BACKUP_DIR=<repo>/backups   OFFSITE_LOG=<repo>/logs/backup_offsite.log
# Chỉ đẩy file đã mã hoá (*.enc, *.sha256). Không bao giờ đẩy khoá. Không in secret.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
[ -f "$HERE/backup_offsite.env" ] && . "$HERE/backup_offsite.env"
APPLY="${OFFSITE_APPLY:-0}"; [ "${1:-}" = "--apply" ] && APPLY=1
MODE="${OFFSITE_MODE:-rclone}"; DEST="${OFFSITE_DEST:-}"; KEEP="${OFFSITE_KEEP:-14}"; TMO="${OFFSITE_TIMEOUT:-900}"
SRC="${BACKUP_DIR:-$ROOT/backups}"
LOG="${OFFSITE_LOG:-$ROOT/logs/backup_offsite.log}"; mkdir -p "$(dirname "$LOG")" 2>/dev/null
STATE="${STATE_DIR:-/var/lib/tradingsys-backup}"
log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG" 2>/dev/null; }
status() { { mkdir -p "$STATE" && echo "$1 $(date +%s) ${2:-}" > "$STATE/offsite.status"; } 2>/dev/null || true; }
fail() { log "FAIL: $*"; status failed "$*"; exit 1; }

[ -d "$SRC" ] || fail "không có thư mục backup $SRC"
case "$KEEP" in ''|*[!0-9]*) fail "OFFSITE_KEEP phải là số";; esac
# Danh sách file cần đẩy: N bản dump mới nhất (+ sha256 + gói cấu hình cùng mốc)
mapfile -t DUMPS < <(ls -1 "$SRC"/ts-2*.dump.enc 2>/dev/null | sort | tail -n "$KEEP")
[ "${#DUMPS[@]}" -gt 0 ] || fail "không có bản dump nào trong $SRC"
FILES=()
for d in "${DUMPS[@]}"; do FILES+=("$(basename "$d")"); [ -f "$d.sha256" ] && FILES+=("$(basename "$d").sha256"); done
mapfile -t CFGS < <(ls -1 "$SRC"/ts-config-*.tar.gz.enc 2>/dev/null | sort | tail -n "$KEEP"); for c in "${CFGS[@]}"; do FILES+=("$(basename "$c")"); done
# kiểm sha256 cục bộ trước khi đẩy (không đẩy file hỏng)
for d in "${DUMPS[@]}"; do [ -f "$d.sha256" ] && { (cd "$SRC" && sha256sum -c "$(basename "$d").sha256" >/dev/null 2>&1) || fail "sha256 cục bộ sai: $(basename "$d")"; }; done

if [ -z "$DEST" ]; then log "DRY-RUN (chưa cấu hình OFFSITE_DEST): sẽ đẩy ${#FILES[@]} file, mode=$MODE, giữ $KEEP bản. Xem docs/BACKUP_OFFSITE.md"; status disabled; printf '  %s\n' "${FILES[@]}"; exit 0; fi
if [ "$APPLY" != 1 ]; then log "DRY-RUN: sẽ đẩy ${#FILES[@]} file -> $DEST (mode=$MODE, giữ $KEEP). Đặt OFFSITE_APPLY=1 hoặc --apply để chạy thật."; printf '  %s\n' "${FILES[@]}"; exit 0; fi

LIST="$(mktemp)"; trap 'rm -f "$LIST"' EXIT; printf '%s\n' "${FILES[@]}" > "$LIST"
export RCLONE_CONFIG="${RCLONE_CONFIG:-/root/.config/tradingsys-rclone.conf}"
case "$MODE" in
  rclone)
    command -v rclone >/dev/null || fail "thiếu rclone"
    timeout "$TMO" rclone copy "$SRC" "$DEST" --files-from "$LIST" --retries 3 --checksum >>"$LOG" 2>&1 || fail "rclone copy lỗi/timeout"
    # kiểm checksum 2 phía (one-way: mọi file nguồn phải có và khớp ở đích)
    timeout "$TMO" rclone check "$SRC" "$DEST" --files-from "$LIST" --one-way >>"$LOG" 2>&1 || fail "rclone check: checksum lệch"
    # giữ N bản ở đích: xoá dump/config cũ hơn các tệp trong danh sách
    timeout "$TMO" rclone lsf "$DEST" --include 'ts-2*.dump.enc*' --include 'ts-config-*.tar.gz.enc' 2>>"$LOG" | sort > "$LIST.remote" || true
    grep -vxFf "$LIST" "$LIST.remote" | while read -r f; do [ -n "$f" ] && timeout 120 rclone deletefile "$DEST/$f" >>"$LOG" 2>&1 && log "đã xoá bản cũ ở đích: $f"; done
    rm -f "$LIST.remote" ;;
  rsync)
    command -v rsync >/dev/null || fail "thiếu rsync"
    SSH="ssh -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new${OFFSITE_SSH_KEY:+ -i $OFFSITE_SSH_KEY}"
    timeout "$TMO" rsync -a --checksum --partial --files-from="$LIST" -e "$SSH" "$SRC/" "$DEST/" >>"$LOG" 2>&1 || fail "rsync lỗi/timeout"
    # kiểm: dry-run checksum không còn gì để truyền
    DIFF="$(timeout "$TMO" rsync -a --checksum -n -i --files-from="$LIST" -e "$SSH" "$SRC/" "$DEST/" 2>>"$LOG" | grep -c '^>f')" || true
    [ "${DIFF:-0}" = 0 ] || fail "rsync check: $DIFF file lệch checksum"
    HOST="${DEST%%:*}"; RPATH="${DEST#*:}"
    # giữ N bản: xoá ở đích file ts-* không nằm trong danh sách
    timeout 120 $SSH "$HOST" "cd '$RPATH' && ls -1 ts-2*.dump.enc* ts-config-*.tar.gz.enc 2>/dev/null" 2>>"$LOG" | sort | grep -vxFf "$LIST" | while read -r f; do
      case "$f" in ts-*) timeout 60 $SSH "$HOST" "rm -f -- '$RPATH/$f'" >>"$LOG" 2>&1 && log "đã xoá bản cũ ở đích: $f";; esac; done ;;
  *) fail "OFFSITE_MODE không hợp lệ: $MODE";;
esac
log "OK: đã đẩy + kiểm checksum ${#FILES[@]} file -> $DEST"; status ok "$DEST"
