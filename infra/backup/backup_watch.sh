#!/usr/bin/env bash
# Giám sát độ tươi backup (timer mỗi giờ): backup >26h, restore-test >8 ngày, đã từng lỗi, off-site cấu hình mà cũ >50h => cảnh báo qua alert-service (dedupe tự có).
# Cũng ghi $STATE_DIR/backup.prom (định dạng Prometheus textfile) cho node_exporter nếu bật textfile collector sau này.
INFRA="$(cd "$(dirname "$0")/.." && pwd)"; STATE="${STATE_DIR:-/var/lib/tradingsys-backup}"; now=$(date +%s)
age() { [ -s "$1" ] && echo $(( now - $(cat "$1") )) || echo -1; }
ba=$(age "$STATE/backup.last_success"); ra=$(age "$STATE/restore_test.last_success")
N() { sh "$INFRA/ops/notify.sh" "$@"; }
if [ "$ba" -lt 0 ] || [ "$ba" -gt $((26*3600)) ]; then N critical "Backup tradingsys quá cũ" "Backup thành công gần nhất cách đây $([ "$ba" -lt 0 ] && echo 'chưa từng' || echo "$((ba/3600))h") (>26h)"; fi
if [ -e "$STATE/backup.last_failure" ]; then N critical "Backup tradingsys lần chạy gần nhất lỗi" "$(cat "$STATE/backup.last_failure")"; fi
if [ "$ra" -lt 0 ] || [ "$ra" -gt $((8*86400)) ]; then N warning "Restore-test backup quá cũ" "Restore-test thành công gần nhất cách đây $([ "$ra" -lt 0 ] && echo 'chưa từng' || echo "$((ra/86400)) ngày") (>8 ngày)"; fi
if [ -e "$STATE/restore_test.last_failure" ]; then N critical "Restore-test lần gần nhất lỗi" "$(cat "$STATE/restore_test.last_failure")"; fi
if [ -f "$STATE/offsite.status" ] && ! grep -q '^disabled' "$STATE/offsite.status"; then
  oa=$(( now - $(awk '{print $2}' "$STATE/offsite.status") )); [ "$oa" -gt $((50*3600)) ] && N warning "Backup off-site quá cũ" "off-site thành công gần nhất cách đây $((oa/3600))h"
fi
wa=$(age "$STATE/wal_archive.last_success")
{ echo "ts_backup_last_success_timestamp $(cat "$STATE/backup.last_success" 2>/dev/null || echo 0)"
  echo "ts_restore_test_last_success_timestamp $(cat "$STATE/restore_test.last_success" 2>/dev/null || echo 0)"
  echo "ts_basebackup_last_success_timestamp $(cat "$STATE/basebackup.last_success" 2>/dev/null || echo 0)"
  echo "ts_pitr_test_last_success_timestamp $(cat "$STATE/pitr_test.last_success" 2>/dev/null || echo 0)"
  echo "ts_backup_last_run_failed $([ -e "$STATE/backup.last_failure" ] && echo 1 || echo 0)"
  echo "ts_restore_test_last_run_failed $([ -e "$STATE/restore_test.last_failure" ] && echo 1 || echo 0)"
  echo "ts_offsite_last_success_timestamp $( [ -f "$STATE/offsite.status" ] && ! grep -q '^disabled' "$STATE/offsite.status" && awk '{print $2}' "$STATE/offsite.status" || echo 0)"
} > "$STATE/backup.prom.tmp" 2>/dev/null && mv "$STATE/backup.prom.tmp" "$STATE/backup.prom"
exit 0
