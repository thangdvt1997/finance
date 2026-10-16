#!/bin/bash
# Chay pytest tung service trong container python:3.12-slim (host chi co py3.10). Dung: bash tests/run_pytest_all.sh [svc ...]  (mac dinh: tat ca)
# Ket qua: $OUT/<svc>.log (mac dinh /tmp/ts-pytest). Copy ma nguon vao container (khong ghi vao repo); bo build/ cu (setuptools dung lai build/lib -> ma cu).
# pattern-research chi mount doc-only data/research/patterns (khong mo test khoa). Tai VPS chia se: nice 15, doi load<=40.
OUT=${OUT:-/tmp/ts-pytest}; R=/root/trading-system; mkdir -p $OUT $OUT/pipc
SVCS=${*:-$(ls $R/services)}
for svc in $SVCS; do
  while [ "$(awk '{print int($1)}' /proc/loadavg)" -gt 40 ]; do sleep 20; done
  MNT=""; EXTRA=""
  [ $svc = pattern-research ] && MNT="-v $R/data/research/patterns:$R/data/research/patterns:ro"
  [ $svc = ai-trading-worker ] && EXTRA="ai-trading pattern-research pattern-engine"
  [ $svc = pattern-scan ] && EXTRA="pattern-render pattern-engine"
  case $svc in client-ui|web-ui) continue;; esac
  timeout 1200 nice -n 15 docker run --rm -e PIP_CACHE_DIR=/pc -v $OUT/pipc:/pc -v $R:/src:ro $MNT python:3.12-slim bash -c "
mkdir -p /w/services /w/infra; cd /w; cp -r /src/libs /src/docs /w/; cp -r /src/mt-agent /w/ 2>/dev/null; cp -r /src/infra/mt-bridge /w/infra/
for x in $svc $EXTRA; do cp -r /src/services/\$x /w/services/; rm -rf /w/services/\$x/build; done; rm -rf /w/libs/common/build
pip install -q --disable-pip-version-check /w/libs/common 'pytest>=8' pytest-asyncio fakeredis httpx >/tmp/pip.log 2>&1
for x in $EXTRA; do [ \$x = pattern-research ] || pip install -q /w/services/\$x >>/tmp/pip.log 2>&1; done
cd /w/services/$svc
if [ $svc = pattern-research ] || [ $svc = ai-trading-worker ]; then pip install -q numpy pandas scipy pyarrow matplotlib pillow >>/tmp/pip.log 2>&1; export PYTHONPATH=/w/services/pattern-research; else pip install -q '.[test]' >>/tmp/pip.log 2>&1; fi
python -m pytest -q --no-header -p no:cacheprovider -rfE tests 2>&1 | tail -60" > $OUT/$svc.log 2>&1
  echo "$svc: $(tail -n 1 $OUT/$svc.log | cut -c1-100)"
done
