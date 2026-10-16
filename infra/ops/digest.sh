#!/bin/bash
# digest.sh - chạy digest.py nhẹ (nice 19, flock, bỏ qua nếu load>60). Cron: /etc/cron.d/tradingsys-digest (mỗi 30 phút).
cd /root/trading-system || exit 1
exec 9>/tmp/ts_digest.lock; flock -n 9 || exit 0
nice -n 19 ionice -c3 timeout 600 python3 infra/ops/digest.py "$@" >> data/la/digest.log 2>&1
nice -n 19 python3 infra/ops/tokens_report.py >> data/la/digest.log 2>&1
