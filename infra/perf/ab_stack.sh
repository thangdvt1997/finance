#!/bin/sh
# Dựng 2 ngăn xếp ĐO RIÊNG (A/B) trên VPS, cô lập khỏi việc recreate web-ui/api-gateway của người khác:
#   TRƯỚC: perf-web-before (nginx với cấu hình git HEAD = chưa cache) -> perf-gw-before (gateway KHÔNG cache)
#   SAU  : perf-web-after  (nginx cấu hình mới)                      -> perf-gw-after  (gateway + Redis cache `redis-cache`)
# Cùng DB/auth/redis bus thật (chỉ đọc), cùng ảnh web-ui => cùng tài nguyên tĩnh. Không đụng container tradingsys-*.
# Dùng:  sh ab_stack.sh up | down | status     (cần: docker build đã chạy: perf-gw-after, perf-web-after; xem build ở dưới)
set -e
ROOT=/root/trading-system; D=/root/qa-e2e; E=/root/perf-env; umask 077; mkdir -p $E
envget() { grep -E "^$1=" $ROOT/infra/.env | head -1 | cut -d= -f2- | tr -d "\"'"; }
dump_env() { docker inspect "$1" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -v -E '^(PATH|HOME|LANG|GPG_KEY|PYTHON_[A-Z_]*|HOSTNAME)=' | grep -v '^$'; }
case "${1:-status}" in
build)
  cd $ROOT && docker build -q -t perf-gw-after -f services/api-gateway/Dockerfile . && docker build -q -t perf-web-after -f services/web-ui/Dockerfile .
  # ảnh gateway "trước" = ảnh đang chạy ở production (cache vô hiệu: thiếu mật khẩu/redis-cache) — gắn thẻ riêng để không bị rebuild đè
  docker tag "$(docker inspect tradingsys-api-gateway-1 --format '{{.Image}}')" perf-gw-before:1 ;;
up)
  dump_env tradingsys-api-gateway-1 | grep -v '^CACHE_' > $E/gw-before.env
  { cat $E/gw-before.env; echo "CACHE_REDIS_URL=redis://ts_cache:$(envget REDIS_CACHE_PASSWORD)@redis-cache:6379/0"; echo "CACHE_ENABLED=1"; } > $E/gw-after.env
  dump_env tradingsys-web-ui-1 > $E/web.env
  [ -f /root/perf-tpl/before.template ] || { echo "thiếu /root/perf-tpl/before.template (git show HEAD:services/web-ui/nginx/default.conf.template)"; exit 1; }
  for v in before after; do
    docker rm -f perf-gw-$v perf-web-$v >/dev/null 2>&1 || true
    CID=$(docker create --name perf-gw-$v --network tradingsys_backend --env-file $E/gw-$v.env --cpus 2 --memory 2g --pids-limit 512 perf-gw-$v:$([ $v = before ] && echo 1 || echo latest))
    for n in ops frontend; do docker network connect tradingsys_$n $CID >/dev/null 2>&1 || true; done
    docker start perf-gw-$v >/dev/null
    TPLMOUNT=""; [ $v = before ] && TPLMOUNT="-v /root/perf-tpl/before.template:/etc/nginx/templates/default.conf.template:ro"
    docker run -d --name perf-web-$v --network tradingsys_frontend --user 101:101 --read-only --cpus 1 --memory 512m --pids-limit 128 \
      --tmpfs /tmp:uid=101,gid=101,mode=1777 --tmpfs /var/cache/nginx:uid=101,gid=101 --tmpfs /etc/nginx/conf.d:uid=101,gid=101 --tmpfs /var/cache/ts-proxy:uid=101,gid=101,size=128m \
      -v $ROOT/infra/web-ui/auth:/etc/nginx/auth:ro $TPLMOUNT --env-file $E/web.env -e GATEWAY_UPSTREAM=http://perf-gw-$v:8000 -e API_PROXY_CACHE=on \
      perf-web-after:latest >/dev/null
  done
  sleep 6; docker ps --filter name=perf- --format '{{.Names}} {{.Status}}' ;;
down)
  docker rm -f perf-gw-before perf-gw-after perf-web-before perf-web-after >/dev/null 2>&1 || true; rm -rf $E; echo down ;;
status) docker ps --filter name=perf- --format '{{.Names}} {{.Status}}' ;;
esac
