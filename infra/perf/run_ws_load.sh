#!/bin/sh
# Chạy TRÊN VPS (host): kiểm thử tải hub realtime với gateway TẠM perf-ws-gw + bộ phát perf-ws-pub (docs/REALTIME.md "Kết quả đo").
#   sh infra/perf/run_ws_load.sh up                          # tạo perf-ws-gw (RT_EXTRA_STREAMS=rt.perf, giới hạn 2 CPU/1 GB) + perf-ws-pub
#   sh infra/perf/run_ws_load.sh run <N> [slow_pct] [dur_s] [rate_tps] [topics]   # một mức tải, ghi CPU/RAM gateway mỗi 5 s
#   sh infra/perf/run_ws_load.sh down                        # dọn: rm perf-ws-*, DEL rt.perf, xoá env tạm
# Env bổ sung cho gateway tạm: GW_ENV="RT_QUOTE_MS=100 ..." ; RT_* ghi đè mặc định. KHÔNG đụng md.quotes/md.bars/account.* (chỉ stream rt.perf).
R=/root/trading-system; OUT=/root/qa-e2e/out; ENVF=$OUT/perf-gw.env; NET=tradingsys_backend; IMG=tradingsys-api-gateway:latest
mkdir -p $OUT
SP=$(docker run --rm --entrypoint python $IMG -c 'import api_gateway,os;print(os.path.dirname(api_gateway.__file__))')   # package trong image; mount đè bằng mã nguồn hiện hành (đo cả bản chưa build)
getenv() { grep "^$1=" $R/infra/.env | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"; }
case "$1" in
up)
  umask 077
  docker inspect tradingsys-api-gateway-1 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(AUTH_TRUST_SECRET|API_TOKENS|REDIS_URL|DATABASE_URL|PORT|SERVICE_NAME|LOG_LEVEL|USER_AGENT)=' > $ENVF
  { echo "CACHE_ENABLED=0"; echo "RT_EXTRA_STREAMS=rt.perf"; echo "RT_MAX_CONNS=3000"; echo "RT_MAX_CONNS_USER=3000"; echo "RT_MAX_CONNS_MASTER=3000"; echo "SERVICE_NAME=perf-ws-gw"; for kv in $GW_ENV; do echo "$kv"; done; } >> $ENVF
  docker rm -f perf-ws-gw >/dev/null 2>&1
  docker run -d --name perf-ws-gw --network $NET --user app --cpus 2 --memory 1g --env-file $ENVF --read-only --tmpfs /tmp --ulimit nofile=65536:65536 -v $R/services/api-gateway/src/api_gateway:$SP:ro -v $R/infra/perf/gw_profile.py:/w/gw_profile.py:ro $IMG ${PROFILE:+python /w/gw_profile.py} >/dev/null
  RP=$(getenv REDIS_APP_PASSWORD)
  docker rm -f perf-ws-pub >/dev/null 2>&1
  docker run -d --name perf-ws-pub --network $NET --user app --cpus 1 --memory 256m -e "REDIS_URL=redis://ts_app:${RP}@redis:6379/0" -v $R/infra/perf/ws_load.py:/w/ws_load.py:ro $IMG python /w/ws_load.py pub --rate "${RATE:-200}" --symbols "${SYMS:-5}" --erate "${ERATE:-20}" --users 100 >/dev/null
  for i in $(seq 1 30); do docker exec perf-ws-gw python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')" >/dev/null 2>&1 && break; sleep 1; done
  docker ps --filter name=perf-ws --format '{{.Names}} {{.Status}}' ;;
run)
  N=${2:-500}; SLOW=${3:-5}; DUR=${4:-60}; RATE=${5:-200}; TOPICS=${6:-5}; PROCS=${PROCS:-4}
  TOK=$(docker inspect perf-ws-gw --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^API_TOKENS=' | cut -d= -f2- | cut -d, -f1)
  SEC=$(docker inspect perf-ws-gw --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^AUTH_TRUST_SECRET=' | cut -d= -f2-)
  F=$OUT/stats_$N.csv; : > $F
  ( while [ ! -f $OUT/.stop_$N ]; do docker stats --no-stream --format '{{.CPUPerc}},{{.MemUsage}}' perf-ws-gw >> $F; sleep 5; done ) &
  SP=$!
  rm -f $OUT/.stop_$N
  docker run --rm --name perf-ws-load-$N --network $NET --user app --cpus 3 --memory 2g --ulimit nofile=65536:65536 -e API_TOKEN="$TOK" -e AUTH_TRUST_SECRET="$SEC" \
    -v $R/infra/perf/ws_load.py:/w/ws_load.py:ro $IMG python /w/ws_load.py load --url ws://perf-ws-gw:8000 --n $N --slow-pct $SLOW --duration $DUR --topics $TOPICS --symbols ${SYMS:-5} --rate $RATE --procs $PROCS --ramp "${RAMP:-100}" ${COMPRESS:+--compress}
  touch $OUT/.stop_$N; wait $SP; rm -f $OUT/.stop_$N
  python3 - "$F" <<'PY'
import sys
cpu=[];mem=[]
for ln in open(sys.argv[1]):
    try:
        c,m=ln.strip().split(",",1); cpu.append(float(c.rstrip("%"))); 
        v=m.split("/")[0].strip(); mem.append(float(v[:-3])*(1024 if v.endswith("GiB") else 1) if v.endswith(("MiB","GiB")) else float(v[:-3])/1024)
    except Exception: pass
cpu.sort()
print("GWSTATS cpu_max=%.0f cpu_p50=%.0f cpu_mean=%.0f mem_max_MiB=%.0f samples=%d"%(max(cpu),cpu[len(cpu)//2],sum(cpu)/len(cpu),max(mem),len(cpu)) if cpu else "GWSTATS none")
PY
  ;;
down)
  docker rm -f perf-ws-gw perf-ws-pub >/dev/null 2>&1; docker ps -a --format '{{.Names}}' | grep '^perf-ws-' | xargs -r docker rm -f >/dev/null 2>&1
  RP=$(getenv REDIS_APP_PASSWORD)
  docker run --rm --network $NET -e "REDISCLI_AUTH=$RP" redis:7-alpine redis-cli -h redis --user ts_app --no-auth-warning DEL rt.perf
  rm -f $ENVF $OUT/stats_*.csv $OUT/.stop_*
  docker ps -a --format '{{.Names}}' | grep -c '^perf-ws-' ;;
esac
