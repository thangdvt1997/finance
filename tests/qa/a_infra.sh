#!/usr/bin/env bash
# QA nhom A (ha tang): chay lai nhanh, chi doc. Dung: bash tests/qa/a_infra.sh
# Kiem: container tradingsys unhealthy/restart, Prometheus targets down + alerts firing, Gatus endpoint fail (10 phut gan nhat),
# dia/RAM/load, top log loi 24h theo service.
P=tradingsys-prometheus-1; fail=0
echo "== container khong healthy/Up =="
docker ps -a --filter label=com.docker.compose.project=tradingsys --format '{{.Names}} {{.Status}}' | grep -E 'unhealthy|Restarting|Exited|starting' && fail=1
echo "== so container tradingsys =="; docker ps --filter label=com.docker.compose.project=tradingsys -q | wc -l
echo "== restart count > 0 =="
for c in $(docker ps --filter label=com.docker.compose.project=tradingsys --format '{{.Names}}'); do n=$(docker inspect -f '{{.RestartCount}}' $c); [ "$n" != 0 ] && echo "$c $n" && fail=1; done
echo "== Prometheus targets down =="
docker exec $P wget -qO- localhost:9090/api/v1/targets | python3 -c "import json,sys;t=json.load(sys.stdin)['data']['activeTargets'];d=[x for x in t if x['health']!='up'];print(len(t),'targets',len(d),'down');[print(x['labels'].get('job'),x['lastError'][:100]) for x in d]" 
echo "== Alerts firing =="
docker exec $P wget -qO- localhost:9090/api/v1/alerts | python3 -c "import json,sys;a=json.load(sys.stdin)['data']['alerts'];[print(x['labels'].get('alertname'),x['state']) for x in a if x['state']=='firing'];print(len(a),'alerts')"
echo "== Gatus fail 10 phut =="
docker logs --since 10m tradingsys-gatus 2>&1 | grep 'success=false' | grep -o 'endpoint=[a-z0-9_-]*' | sort | uniq -c
echo "== dia/RAM/load =="; df -h / | tail -1; free -m | sed -n 2p; uptime
echo "== top loi 24h =="
for c in $(docker ps --filter label=com.docker.compose.project=tradingsys --format '{{.Names}}' | grep -v gatus); do n=$(docker logs --since 24h $c 2>&1 | grep -c -i -E 'traceback|exception|\bERROR\b|critical'); echo "$n $c"; done | sort -rn | head -8
exit $fail
