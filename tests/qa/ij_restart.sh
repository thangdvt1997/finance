#!/bin/sh
# IJ-I: restart TỪNG container tradingsys (docker restart, không build) và đo thời gian phục hồi (healthy/running ổn định).
# Dùng: ij_restart.sh <container>... ; KHÔNG dùng flock deploy (hàng đợi deploy có thể chờ hàng chục phút); không restart service đang được deploy. Kết quả: "<tên> <giây-đến-healthy> <trạng-thái>"
for n in "$@"; do
  docker restart "$n" >/dev/null 2>&1 || { echo "$n - RESTART_FAIL"; continue; }
  t0=$(date +%s); st=""
  while [ $(( $(date +%s) - t0 )) -lt 180 ]; do
    st=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$n")
    { [ "$st" = healthy ] || [ "$st" = running ]; } && break; sleep 2
  done
  sleep 5; rc=$(docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' "$n")
  echo "$n $(( $(date +%s) - t0 ))s $st $rc errlog=$(docker logs --since 20s "$n" 2>&1 | grep -c -i -E 'traceback|error|fatal')"
done
