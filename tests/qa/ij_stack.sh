#!/bin/sh
# IJ-I: restart cả stack tradingsys theo thứ tự phụ thuộc (docker restart từng container, không build):
# DB/redis -> auth/gateway -> pipeline dữ liệu -> dịch vụ nghiệp vụ -> UI -> giám sát. Đo thời gian tới healthy từng cái.
# Chỉ chạy khi các agent khác đã xong. Dùng: ij_stack.sh   (in "<tên> <giây> <trạng thái>")
D="$(cd "$(dirname "$0")" && pwd)"
ORDER="timescaledb-1 redis-1 redis-cache-1 auth api-gateway-1 mt-bridge-1 market-collector-1 storage-writer-1 news-collector-1 expert-collector-1 nlp vn-market data-keeper pattern-engine pattern-scan ai-trading ai-trading-worker paper-trader analytics journal track-record risk-monitor-1 alert-service-1 alert-rules briefing reporter-1 web-ui-1 client-ui-1 prometheus-1 alertmanager-1 grafana-1"
for s in $ORDER; do "$D/ij_restart.sh" "tradingsys-$s"; done
