#!/bin/sh
# Chay tren VPS host: publish 3 luong song song, restart roi SIGKILL storage-writer giua luong.
# CHI tac dong container tradingsys-storage-writer-1 (restart policy unless-stopped tu dong dung lai sau kill).
D=/root/qa-e2e
SW=tradingsys-storage-writer-1
rm -f $D/out/crash_flag_30 $D/out/crash_flag_65
docker rm -f qa-crash >/dev/null 2>&1
docker run -d --name qa-crash --network tradingsys_backend --env-file /root/trading-system/infra/.env \
  -e QA_OUT=/qa/out -e PIP_CACHE_DIR=/qa/pip -e PYTHONPATH=/qa -v $D:/qa -w /qa python:3.12-slim \
  sh -c "pip install -q --disable-pip-version-check redis asyncpg httpx websockets >/dev/null 2>&1; python -u /qa/test_load.py crash" >/dev/null
for n in ops frontend internal; do docker network inspect tradingsys_$n >/dev/null 2>&1 && docker network connect tradingsys_$n qa-crash >/dev/null 2>&1; done
i=0; while [ ! -f $D/out/crash_flag_30 ] && [ $i -lt 600 ]; do sleep 0.2; i=$((i+1)); done
echo "[$(date -u +%T)] RESTART $SW (SIGTERM, graceful)"; docker restart $SW >/dev/null
i=0; while [ ! -f $D/out/crash_flag_65 ] && [ $i -lt 600 ]; do sleep 0.2; i=$((i+1)); done
echo "[$(date -u +%T)] SIGKILL tien trinh $SW tu host (crash that)"; PID=$(docker inspect -f '{{.State.Pid}}' $SW); kill -9 $PID  # SIGKILL tien trinh that tu host (giong crash/OOM; khong qua Docker API)
sleep 12; ST=$(docker inspect -f '{{.State.Status}}' $SW); echo "[$(date -u +%T)] sau KILL 12s: $ST restarts=$(docker inspect -f '{{.RestartCount}}' $SW)"
if [ "$ST" != "running" ]; then echo "restart policy KHONG tu dung lai -> docker start thu cong"; docker start $SW >/dev/null; fi
docker wait qa-crash >/dev/null
docker logs qa-crash 2>&1 | tail -40
docker rm qa-crash >/dev/null
docker inspect -f '{{.State.Status}} health={{.State.Health.Status}}' $SW
