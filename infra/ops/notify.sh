#!/bin/sh
# Gửi cảnh báo từ host vào alert-service (-> alerts.out -> dedupe/rate-limit -> Telegram/ntfy). Dùng: notify.sh <critical|warning|info> <tiêu đề> <nội dung> [resolved]
# Không phụ thuộc mật khẩu Redis (đi qua webhook của alert-service trong container). Lỗi gửi không làm hỏng script gọi.
SEV="${1:-warning}"; TITLE="${2:-ts alert}"; BODY="${3:-}"; ST="${4:-firing}"
C="${ALERT_CONTAINER:-tradingsys-alert-service-1}"
docker exec -i -e SEV="$SEV" -e TITLE="$TITLE" -e BODY="$BODY" -e ST="$ST" "$C" python - <<'PY' || echo "notify: không gửi được ($TITLE)" >&2
import json, os, urllib.request
p = {"alerts": [{"status": os.environ["ST"], "labels": {"alertname": os.environ["TITLE"], "severity": os.environ["SEV"], "service": "backup"},
                 "annotations": {"summary": os.environ["TITLE"], "description": os.environ["BODY"]}}]}
h = {"Content-Type": "application/json"}
t = os.environ.get("ALERT_WEBHOOK_TOKEN") or os.environ.get("WEBHOOK_TOKEN")
if t: h["Authorization"] = "Bearer " + t
if os.environ.get("INTERNAL_TOKEN"): h["X-Internal-Token"] = os.environ["INTERNAL_TOKEN"]
urllib.request.urlopen(urllib.request.Request("http://localhost:8000/webhook/alertmanager", json.dumps(p).encode(), h), timeout=10).read()
PY
exit 0
