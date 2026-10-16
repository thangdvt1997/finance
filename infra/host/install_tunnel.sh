#!/usr/bin/env bash
# Cài unit systemd riêng `tradingsys-tunnel.service` (cloudflared quick tunnel -> TUNNEL_TARGET).
# Mặc định chỉ CÀI, KHÔNG bật (tunnel công khai chỉ bật khi web-ui đã có basic auth).
#   sudo infra/host/install_tunnel.sh            # cài unit, chưa chạy
#   sudo infra/host/install_tunnel.sh --start    # cài + chạy (+ enable khi boot)
#   TUNNEL_TARGET=http://127.0.0.1:3300 ...      # đổi đích (mặc định web-ui 127.0.0.1:8580)
# Dừng: systemctl disable --now tradingsys-tunnel ; xem URL: cat /root/trading-system/data/tunnel_url.txt
set -euo pipefail
ROOT="${TS_ROOT:-/root/trading-system}"
TARGET="${TUNNEL_TARGET:-http://127.0.0.1:8580}"
mkdir -p "$ROOT/data"
chmod +x "$ROOT/infra/host/tunnel_url.sh"
echo "TUNNEL_TARGET=$TARGET" > /etc/default/tradingsys-tunnel
cat > /etc/systemd/system/tradingsys-tunnel.service <<UNIT
[Unit]
Description=tradingsys Cloudflare quick tunnel (web-ui, URL -> $ROOT/data/tunnel_url.txt)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/etc/default/tradingsys-tunnel
# Quick tunnel: không cần tài khoản, URL https://*.trycloudflare.com đổi mỗi lần restart.
ExecStartPre=/bin/sh -c ': > $ROOT/data/tunnel.log; rm -f $ROOT/data/tunnel_url.txt'
ExecStart=/bin/sh -c 'exec /usr/local/bin/cloudflared tunnel --no-autoupdate --url \$TUNNEL_TARGET >> $ROOT/data/tunnel.log 2>&1'
ExecStartPost=/bin/sh -c 'for i in \$(seq 1 30); do sleep 2; TS_ROOT=$ROOT $ROOT/infra/host/tunnel_url.sh && exit 0; done; exit 0'
ExecStopPost=/bin/rm -f $ROOT/data/tunnel_url.txt
Restart=always
RestartSec=10
Nice=10

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
if [ "${1:-}" = "--start" ]; then
  systemctl enable --now tradingsys-tunnel.service
  sleep 1; cat "$ROOT/data/tunnel_url.txt" 2>/dev/null || echo "(URL chưa có, xem $ROOT/data/tunnel.log)"
else
  echo "Đã cài unit (chưa chạy). Bật: systemctl enable --now tradingsys-tunnel"
fi
