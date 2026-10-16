#!/bin/sh
# Chay tren VPS <VPS_IP>: container TAM `mtload-*` (khong mang, khong Redis/DB, gioi han CPU/RAM), don dep khi xong.
#   sh services/mt-bridge/loadtest/run_loadtest.sh        (ROOT=/root/trading-system)
ROOT="${TS_ROOT:-/root/trading-system}"
IMG="${MT_BRIDGE_IMAGE:-tradingsys-mt-bridge}"
N="${N:-200}"
NAME="mtload-$$"
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1; }
trap cleanup EXIT
docker run -d --name "$NAME" --network none --cpus 2 -m 768m --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true \
  -v "$ROOT/services/mt-bridge/loadtest/mtload.py:/mtload.py:ro" --entrypoint python "$IMG" /mtload.py server -n "$N" >/dev/null
sleep 10
rc=0
docker exec "$NAME" python /mtload.py gen -n 50 --interval 1 --dur 30 || rc=1
docker exec "$NAME" python /mtload.py gen -n 200 --interval 1 --dur 45 || rc=1
docker exec "$NAME" python /mtload.py gen -n 200 --interval 0.4 --dur 30 || rc=1
docker exec "$NAME" python /mtload.py gen -n 200 --interval 1 --dur 40 --mixed || rc=1
docker exec "$NAME" python - <<'PY'
import json,urllib.request
print("cuoi:", json.load(urllib.request.urlopen("http://127.0.0.1:18000/_stats")))
PY
docker stats --no-stream --format 'cpu={{.CPUPerc}} mem={{.MemUsage}}' "$NAME"
exit $rc
