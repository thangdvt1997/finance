#!/bin/sh
# Chay kich ban QA nhom C trong container tam (mang tradingsys). Dung: sh tests/qa/c_run.sh <script tu goc repo, vd tests/e2e/test_pentest_authz.py | tests/qa/auth/c_xxx.py>
R=/root/trading-system
S="$1"; shift
OUT=${QA_OUT_HOST:-/tmp/qa_c_out}; mkdir -p $OUT/pip
CID=$(docker create --network tradingsys_backend --env-file $R/infra/.env \
  -e QA_OUT=/out -e PIP_CACHE_DIR=/out/pip -e PYTHONPATH=/qa/tests/e2e -v $R:/qa:ro -v $OUT:/out -w /qa python:3.12-slim \
  sh -c "pip install -q --disable-pip-version-check redis asyncpg httpx websockets argon2-cffi pyotp >/dev/null 2>&1; python -u /qa/$S $*")
for n in ops frontend internal; do docker network inspect tradingsys_$n >/dev/null 2>&1 && docker network connect tradingsys_$n $CID >/dev/null 2>&1; done
docker start -a $CID; rc=$?
docker rm -f $CID >/dev/null 2>&1
exit $rc
