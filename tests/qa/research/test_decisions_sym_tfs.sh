#!/usr/bin/env bash
# Hồi quy: data/decisions != 5xx; analytics/symbol mã lạ không 404; EURUSD có MN1 trong /symbols.tfs
B=${B:-http://localhost:8080/api/v1}; fail=0
c=$(curl -s -o /dev/null -w %{http_code} "$B/analytics/symbol/ZZZNONE?tf=H1"); [ "$c" = 200 ] || { echo "FAIL analytics symbol $c"; fail=1; }
curl -s "$B/symbols" | grep -q '"MN1"' || { echo "FAIL MN1 not in symbols.tfs"; fail=1; }
c=$(docker exec tradingsys-data-keeper python -c "import urllib.request as u;print(u.urlopen('http://localhost:8000/v1/data/decisions').status)" 2>&1|tail -1); [ "$c" = 200 ] || { echo "FAIL decisions: $c"; fail=1; }
exit $fail
