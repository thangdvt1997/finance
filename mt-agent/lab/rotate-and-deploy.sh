#!/bin/bash
# xoay token MT (khong in ra) + build lai chi mt-bridge + cap nhat secrets cua mtlab
set -e
cd /root/trading-system/infra
cp .env /root/mtlab/out/env.bak.$(date +%s) 2>/dev/null || true
for k in MT_TOKEN_DEMO_MT4_01 MT_TOKEN_DEMO_MT5_01; do
  v=$(openssl rand -hex 24)
  sed -i "s/^$k=.*/$k=$v/" .env
done
docker compose -p tradingsys build mt-bridge 2>&1 | tail -2
docker compose -p tradingsys up -d --no-deps mt-bridge 2>&1 | tail -2
grep -E '^MT_TOKEN_DEMO_MT4_01=' .env > /root/mtlab/secrets-mt4.env
grep -E '^MT_TOKEN_DEMO_MT5_01=' .env > /root/mtlab/secrets-mt5.env
chmod 600 /root/mtlab/secrets-*.env
