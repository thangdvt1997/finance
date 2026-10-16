#!/bin/sh
# Sinh HMAC secret cho tài khoản mt-bridge vào infra/.env nếu thiếu (không in giá trị). Dùng: sh infra/ops/gen_mt_hmac.sh [MT_HMAC_DEMO_MT4_01 ...]
cd "$(dirname "$0")/.."
VARS="${*:-MT_HMAC_DEMO_MT4_01 MT_HMAC_DEMO_MT5_01}"
for v in $VARS; do
  grep -q "^$v=." .env || { printf '\n%s=%s\n' "$v" "$(openssl rand -hex 32)" >> .env; echo "đã thêm $v vào .env"; }
done
