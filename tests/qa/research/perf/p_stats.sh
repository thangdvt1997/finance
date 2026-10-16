#!/bin/sh
# P-003: lay mau docker stats + restart/OOM cac container tradingsys. Dung: p_stats.sh <nhan> ; ghi vao data/research/program/perf/stats_<nhan>.txt
D=/root/trading-system/data/research/program/perf; L=${1:-s}
{ date -Is; uptime; nice -n 19 timeout 120 docker stats --no-stream --format '{{.Name}} {{.CPUPerc}} {{.MemUsage}} {{.MemPerc}}' | grep tradingsys | sort
  echo '--restarts/oom'; for c in $(docker ps -a --format '{{.Names}}' | grep '^tradingsys'); do docker inspect -f '{{.Name}} rc={{.RestartCount}} oom={{.State.OOMKilled}} started={{.State.StartedAt}}' $c; done; } > $D/stats_$L.txt
