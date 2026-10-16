#!/bin/bash
# Chay nen sau khi terminal len: (1) them URL WebRequest bang GUI (danh sach nay khong tu giu qua restart trong moi truong nay)
# (2) MT4 che do smoke: chay script MTAgentSmoke. Phu thuoc toa do man hinh 1280x800.
export DISPLAY=:1
K=$1; URL=${2:-http://bridge.lab}
for i in $(seq 1 90); do xdotool search --name "MetaTrader" >/dev/null 2>&1 && break; sleep 2; done
sleep 25
if [ "$K" = mt5 ]; then
  /mtlab/allow-url.sh "$URL"
else
  /mtlab/allow-url-mt4.sh "$URL"
  if [ "${MT_MODE:-ea}" = smoke ]; then sleep 3; /mtlab/run-script-mt4.sh; fi
fi
echo "post-start done $(date +%T)"
