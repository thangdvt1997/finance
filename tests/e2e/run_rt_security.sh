#!/bin/sh
# Chạy TRÊN VPS: sh /root/qa-e2e/run_rt_security.sh   — dựng 2 gateway TẠM (perf-ws-gw-sec, perf-ws-gw-age; RT_EXTRA_STREAMS=rt.sec), chạy test_realtime_security.py, dọn sạch.
# Mã gateway lấy từ /root/trading-system (mount đè package trong image) để kiểm cả bản chưa build lại. Bí mật chỉ nằm trong file env 600 tạm, xoá ở cuối.
D=${QA_DIR:-/root/qa-e2e}; R=/root/trading-system; IMG=tradingsys-api-gateway:latest; NET=tradingsys_backend
SP=$(docker run --rm --entrypoint python $IMG -c 'import api_gateway,os;print(os.path.dirname(api_gateway.__file__))')
umask 077; mkdir -p $D/out
G=$D/out/rtsec-gw.env; T=$D/out/rtsec-test.env
docker inspect tradingsys-api-gateway-1 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(AUTH_TRUST_SECRET|API_TOKENS|REDIS_URL|DATABASE_URL|PORT|LOG_LEVEL|USER_AGENT)=' > $G
echo "CACHE_ENABLED=0" >> $G; echo "RT_EXTRA_STREAMS=rt.sec" >> $G
RP=$(grep '^REDIS_APP_PASSWORD=' $R/infra/.env | head -1 | cut -d= -f2- | tr -d "\"'")
{ echo "API_TOKEN=$(grep '^API_TOKENS=' $G | cut -d= -f2- | cut -d, -f1)"; grep '^AUTH_TRUST_SECRET=' $G; echo "REDIS_URL=redis://ts_app:${RP}@redis:6379/0"; } > $T
run_gw() { docker rm -f $1 >/dev/null 2>&1; shift_name=$1; docker run -d --name "$shift_name" --network $NET --user app --cpus 2 --memory 768m --env-file $G $2 -v $R/services/api-gateway/src/api_gateway:$SP:ro --read-only --tmpfs /tmp $IMG >/dev/null; }
run_gw perf-ws-gw-sec "-e RT_MAX_CONNS_USER=6"
run_gw perf-ws-gw-age "-e RT_MAX_AGE_S=4"
for n in perf-ws-gw-sec perf-ws-gw-age; do ok=0; for i in $(seq 1 120); do docker exec $n python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')" >/dev/null 2>&1 && { ok=1; break; }; sleep 1; done; [ $ok = 1 ] || echo "CANH BAO: $n chua san sang sau 120s (may qua tai?)"; done
CID=$(docker create --network $NET --env-file $T -e QA_OUT=/qa/out -e PIP_CACHE_DIR=/qa/pip -e PYTHONPATH=/qa -v $D:/qa -w /qa python:3.12-slim \
  sh -c "pip install -q --disable-pip-version-check redis asyncpg httpx websockets >/dev/null 2>&1; python -u /qa/test_realtime_security.py")
for n in frontend ops; do docker network connect tradingsys_$n $CID >/dev/null 2>&1; done
docker start -a $CID; rc=$?
docker rm -f $CID perf-ws-gw-sec perf-ws-gw-age >/dev/null 2>&1
rm -f $G $T
docker ps -a --format '{{.Names}}' | grep -c '^perf-ws-' | sed 's/^/perf-ws-* còn lại: /'
exit $rc
