#!/usr/bin/env bash
# Cài các systemd timer cho tradingsys (tiền tố tradingsys-): backup 03:10 UTC hằng ngày, restore-test Chủ nhật 04:30, base backup Chủ nhật 02:30,
# watch độ tươi mỗi giờ. Chạy bằng root trên VPS. Idempotent.
set -euo pipefail
ROOT="${TS_ROOT:-/root/trading-system}"
chmod +x "$ROOT/infra/backup/"*.sh "$ROOT/infra/ops/"*.sh
mkdir -p /var/lib/tradingsys-backup
mk() { # name desc exec calendar [extra-timer-lines]
  cat > "/etc/systemd/system/tradingsys-$1.service" <<UNIT
[Unit]
Description=tradingsys $2
After=docker.service
[Service]
Type=oneshot
ExecStart=$3
Nice=10
TimeoutStartSec=3h
UNIT
  cat > "/etc/systemd/system/tradingsys-$1.timer" <<UNIT
[Unit]
Description=tradingsys $2
[Timer]
OnCalendar=$4
Persistent=true
RandomizedDelaySec=120
[Install]
WantedBy=timers.target
UNIT
}
mk backup "backup TimescaleDB (pg_dump mã hoá, off-site nếu cấu hình)" "$ROOT/infra/backup/pg_backup.sh" "*-*-* 03:10:00 UTC"
mk restoretest "restore-test backup (dump + PITR vào DB/container tạm)" "/bin/bash -c '$ROOT/infra/backup/pg_restore_test.sh; $ROOT/infra/backup/pitr_restore_test.sh'" "Sun *-*-* 04:30:00 UTC"
mk basebackup "base backup vật lý (PITR)" "$ROOT/infra/backup/pg_basebackup.sh" "Sun *-*-* 02:30:00 UTC"
mk backupwatch "giám sát độ tươi backup" "$ROOT/infra/backup/backup_watch.sh" "*-*-* *:17:00 UTC"
systemctl daemon-reload
for t in backup restoretest basebackup backupwatch; do systemctl enable --now "tradingsys-$t.timer"; done
systemctl list-timers 'tradingsys-*' --no-pager
