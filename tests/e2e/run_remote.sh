#!/bin/sh
# Chay tren VPS (host): sh /root/qa-e2e/run_remote.sh <script.py> [args...]
# Container tam python:3.12-slim noi vao cac network tradingsys_backend (redis/timescaledb) + ops (service HTTP) + frontend (web-ui) + internal (mt-bridge);
# docker run chi gan 1 mang nen dung create -> network connect -> start. Secret lay tu infra/.env (khong in ra).
D=${QA_DIR:-/root/qa-e2e}
mkdir -p $D/out $D/pip
S="$1"; shift
CID=$(docker create --network tradingsys_backend --env-file /root/trading-system/infra/.env \
  -e QA_OUT=/qa/out -e PIP_CACHE_DIR=/qa/pip -e PYTHONPATH=/qa -v $D:/qa -w /qa python:3.12-slim \
  sh -c "pip install -q --disable-pip-version-check redis asyncpg httpx websockets >/dev/null 2>&1; python -u /qa/$S $*")
for n in ops frontend internal; do docker network inspect tradingsys_$n >/dev/null 2>&1 && docker network connect tradingsys_$n $CID >/dev/null 2>&1; done
docker start -a $CID; rc=$?
docker rm -f $CID >/dev/null 2>&1
exit $rc
