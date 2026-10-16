#!/bin/sh
# Lấy URL trycloudflare mới nhất từ log tunnel, ghi ra data/tunnel_url.txt (exit 0 nếu có).
ROOT="${TS_ROOT:-/root/trading-system}"
URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$ROOT/data/tunnel.log" 2>/dev/null | tail -1)
[ -n "$URL" ] || exit 1
echo "$URL" > "$ROOT/data/tunnel_url.txt"
