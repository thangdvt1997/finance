#!/bin/sh
# P-002: tai nhe co kiem soat (tai dung ij_load.py): USERS nguoi dung ao (mac dinh 10) + 5 WS, SECONDS giay (mac dinh 150). Watchdog: load1>40 -> kill.
# Can PERF_USER/PERF_PASS (master thu). Ra data/research/program/perf/load.json + load_watch.txt
D=/root/trading-system/data/research/program/perf; SRC=$(cd "$(dirname "$0")" && pwd)
( while :; do L=$(cut -d' ' -f1 /proc/loadavg); echo "$(date +%T) load1=$L" >> $D/load_watch.txt; [ "${L%.*}" -gt 40 ] && { echo ABORT >> $D/load_watch.txt; pkill -f ij_load.py; break; }; sleep 5; done ) &
W=$!
IJ_USER=$PERF_USER IJ_PASS=$PERF_PASS nice -n 19 timeout $((${2:-150}+60)) python3 $SRC/../../ij_load.py "${BASE:-http://127.0.0.1:8580}" "${1:-10}" "${2:-150}" > $D/load.json; kill $W 2>/dev/null; cat $D/load.json
