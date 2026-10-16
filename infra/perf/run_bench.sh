#!/bin/sh
# Chạy TRÊN VPS: sh /root/trading-system/infra/perf/run_bench.sh <label> [MODE=web|gw] [ONLY=ep1,ep2] [VUS=200] [DUR=15s] [GAP=12]
#   MODE=web (mặc định): qua nginx web-ui với phiên QA (cookie)  — đo cả nginx/auth_request/cache nginx
#   MODE=gw            : thẳng api-gateway:8000 với X-API-Key (principal service) — cô lập khỏi việc recreate web-ui của agent khác
# Cần: tests/e2e/*.py đã đẩy lên /root/qa-e2e (tests/e2e/deploy.sh). Kết quả: /root/qa-e2e/out/bench_<label>.json. Container tạm perf-k6; phiên QA luôn bị xoá ở cuối.
L="${1:-run}"; shift
D=/root/qa-e2e; P=/root/trading-system/infra/perf
BASE=http://web-ui:8080; COOKIE=""; AK=""
case " $* " in *" MODE=gw "*) BASE=http://api-gateway:8000; AK=$(grep -E '^API_TOKEN=' /root/trading-system/infra/.env | head -1 | cut -d= -f2- | tr -d "\"'") ;; esac
if [ -z "$AK" ]; then
  cp $P/perf_session.py $D/perf_session.py; mkdir -p $D/out
  sh $D/run_remote.sh perf_session.py setup || exit 1
  COOKIE=$(cat $D/out/perf.cookie)
fi
docker image inspect grafana/k6:latest >/dev/null 2>&1 || docker pull -q grafana/k6:latest >/dev/null
ENVS=""; for kv in "$@"; do ENVS="$ENVS -e $kv"; done
docker run --rm --user 0 --name perf-k6 --network tradingsys_frontend -v $P:/s:ro -v $D/out:/out -e BASE="$BASE" -e COOKIE="$COOKIE" -e API_KEY="$AK" -e LABEL="$L" $ENVS grafana/k6:latest run -q /s/bench.js
rc=$?
[ -z "$AK" ] && sh $D/run_remote.sh perf_session.py cleanup
exit $rc
