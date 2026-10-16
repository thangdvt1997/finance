#!/bin/sh
# Mo phong consumer chet giu PEL: container phu qa-sw (image tradingsys-storage-writer, cung group) bi SIGKILL giua luong.
# Khong dung vao tradingsys-storage-writer-1. Moi message that bi ket se duoc phat lai (recover).
D=/root/qa-e2e; ENVF=/root/trading-system/infra/.env
g() { grep -E "^$1=" $ENVF | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }
DBURL="postgresql://$(g POSTGRES_USER):$(g POSTGRES_PASSWORD)@timescaledb:5432/$(g POSTGRES_DB)"
IMG=$(docker inspect -f '{{.Config.Image}}' tradingsys-storage-writer-1)
docker rm -f qa-sw >/dev/null 2>&1
docker run -d --name qa-sw --hostname qa-sw-$$ --network tradingsys_backend -e REDIS_URL="redis://ts_app:$(g REDIS_APP_PASSWORD)@redis:6379/0" -e DATABASE_URL="$DBURL" \
  -e CONSUMER_NAME=qa-sw-$$ -e PORT=8000 -e SERVICE_NAME=qa-sw -e LOG_LEVEL=WARNING $IMG >/dev/null
sleep 6
rm -f $D/out/orphan_flag
sh $D/run_remote.sh test_orphan_pel.py publish &
i=0; while [ ! -f $D/out/orphan_flag ] && [ $i -lt 300 ]; do sleep 0.05; i=$((i+1)); done
sleep ${ORPHAN_DELAY:-0.6}
docker kill -s KILL qa-sw >/dev/null; echo "[$(date -u +%T)] SIGKILL qa-sw"
wait
docker rm -f qa-sw >/dev/null
# H1 da sua: consumer co dinh 'storage-writer-1' + XAUTOCLAIM (idle>=60s, quet moi 30s) => cho ~100s de worker that nhat lai PEL cua qa-sw
sleep ${ORPHAN_WAIT:-100}
sh $D/run_remote.sh test_orphan_pel.py inspect 2>&1 | grep -E 'PASS|FAIL|INFO|METRIC'
sh $D/run_remote.sh test_orphan_pel.py recover 2>&1 | tail -3
sh $D/run_remote.sh cleanup.py 2>&1 | tail -1
