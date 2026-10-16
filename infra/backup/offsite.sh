#!/usr/bin/env bash
# Đẩy bản backup MÃ HOÁ ra ngoài ổ/host bằng rclone. KHÔNG bịa đích: chỉ chạy khi người dùng cấu hình infra/backup/offsite.env
# (xem offsite.env.example). Chưa cấu hình => ghi trạng thái "disabled" và thoát 0.
#   BACKUP_RCLONE_REMOTE=remote:bucket/tradingsys     (remote tạo bằng `rclone config --config $RCLONE_CONFIG`)
#   RCLONE_CONFIG=/root/.config/tradingsys-rclone.conf  (tách riêng, không đụng cấu hình rclone của hệ thống khác)
set -euo pipefail
OUT_DIR="${1:?usage: offsite.sh <backup_dir>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
STATE="${STATE_DIR:-/var/lib/tradingsys-backup}"; mkdir -p "$STATE"
[ -f "$HERE/offsite.env" ] && . "$HERE/offsite.env"
if [ -z "${BACKUP_RCLONE_REMOTE:-}" ]; then echo "disabled $(date +%s)" > "$STATE/offsite.status"; echo "offsite: chưa cấu hình (bỏ qua)"; exit 0; fi
export RCLONE_CONFIG="${RCLONE_CONFIG:-/root/.config/tradingsys-rclone.conf}"
# copy (không sync/xoá): giữ lịch sử phía đích; đích tự áp retention (lifecycle) hoặc dùng `rclone delete --min-age`.
rclone copy "$OUT_DIR" "$BACKUP_RCLONE_REMOTE" --include 'ts-2*.dump.enc' --include 'ts-2*.dump.enc.sha256' --include 'ts-config-*.tar.gz.enc' --max-age "${OFFSITE_MAX_AGE:-3d}" --retries 3
echo "ok $(date +%s) $BACKUP_RCLONE_REMOTE" > "$STATE/offsite.status"
echo "offsite ok -> $BACKUP_RCLONE_REMOTE"
