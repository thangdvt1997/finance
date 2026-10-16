#!/bin/bash
# kiem tra end-to-end tren VPS (khong in token)
cd /root/trading-system/infra
T=$(grep -E '^BRIDGE_ADMIN_TOKEN=' .env | cut -d= -f2-)
export REDISCLI_AUTH=$(grep -E '^REDIS_ADMIN_PASSWORD=' .env | cut -d= -f2-)   # ACL: user ts_admin (khong in)
RC="docker exec -e REDISCLI_AUTH tradingsys-redis-1 redis-cli --no-auth-warning --user ts_admin"
echo "--- /accounts"; if [ -n "$T" ]; then curl -s -H "Authorization: Bearer $T" 127.0.0.1:8490/accounts; else curl -s 127.0.0.1:8490/accounts; fi | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d)[:1500])"
echo; echo "--- redis streams"
for s in account.snapshots md.quotes md.bars alerts.out; do printf "%s: " $s; $RC XLEN $s; done
echo "--- postgres"
docker exec tradingsys-timescaledb-1 psql -U ts -d ts -c "\dt" 2>&1 | head -30
