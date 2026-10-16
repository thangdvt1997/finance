#!/bin/sh
# P-005: chay p_pages.mjs trong container playwright tam (nice 19, 1 CPU, 2g), master thu qa-perf-pg (tao/xoa). Load1>40 -> khong chay.
SRC="$(cd "$(dirname "$0")" && pwd)"; MU="$SRC/../../../../services/web-ui/qa/master_user.py"; NAME=qa-perf-pg; W=/tmp/qa-perf-pg
[ "$(cut -d. -f1 /proc/loadavg)" -gt 40 ] && { echo "load>40, bo qua"; exit 3; }
mkdir -p "$W" && chmod 700 "$W" && cp "$SRC/p_pages.mjs" "$W/"
docker exec -i tradingsys-auth python - delete $NAME < "$MU" >/dev/null 2>&1 || true
docker exec -i tradingsys-auth python - create $NAME < "$MU" > "$W/pw.txt"; chmod 600 "$W/pw.txt"
timeout 600 nice -n 19 docker run --rm --name "$NAME-pw" --cpus 1 --memory 2g --network host -v "$W:/work" -w /work -e BASE="${BASE:-http://127.0.0.1:8580}" -e QA_USER=$NAME \
  mcr.microsoft.com/playwright:v1.49.0-jammy sh -c "[ -d node_modules/playwright ] || npm i --no-save --silent playwright@1.49.0 >/dev/null 2>&1; QA_PASS=\$(cat pw.txt) node p_pages.mjs" | tee /root/trading-system/data/research/program/perf/pages.json
docker exec -i tradingsys-auth python - delete $NAME < "$MU" >/dev/null 2>&1; rm -rf "$W/pw.txt"
