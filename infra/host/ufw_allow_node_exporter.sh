#!/usr/bin/env bash
# Cho Prometheus của tradingsys (subnet mạng tradingsys_internal) scrape node_exporter có sẵn trên host (:9100).
# ufw đang INPUT DROP nên container không tới được host:9100 nếu không có luật này. Chỉ mở cho đúng subnet đó.
set -euo pipefail
SUBNET=$(docker network inspect tradingsys_internal -f '{{(index .IPAM.Config 0).Subnet}}')
ufw allow from "$SUBNET" to any port 9100 proto tcp comment 'tradingsys prometheus -> node_exporter'
echo "ok: $SUBNET -> 9100"
