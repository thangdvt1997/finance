#!/bin/sh
# Chạy TRÊN VPS: sh /root/trading-system/infra/perf/run_pageload.sh <label> [N=5] [PAGES=/,/#/intel]
# Playwright 1.49 (image đã có sẵn trên VPS) trong container tạm perf-pl-* nối mạng frontend; phiên QA tạo/xoá như run_bench.sh. Kết quả: /root/qa-e2e/out/pageload_<label>.json
L="${1:-run}"; shift
D=/root/qa-e2e; P=/root/trading-system/infra/perf
cp $P/perf_session.py $D/perf_session.py; mkdir -p $D/out /tmp/perf-pl && cp $P/pageload.mjs /tmp/perf-pl/
sh $D/run_remote.sh perf_session.py setup || exit 1
COOKIE=$(cat $D/out/perf.cookie)
ENVS=""; for kv in "$@"; do ENVS="$ENVS -e $kv"; done
docker run --rm --name perf-pl-$$ --network tradingsys_frontend -v /tmp/perf-pl:/work -v $D/out:/out -w /work -e BASE=http://web-ui:8080 -e COOKIE="$COOKIE" -e LABEL="$L" $ENVS \
  mcr.microsoft.com/playwright:v1.49.0-jammy sh -c "[ -d node_modules/playwright ] || npm i --no-save --silent playwright@1.49.0; node pageload.mjs"
rc=$?
sh $D/run_remote.sh perf_session.py cleanup
exit $rc
