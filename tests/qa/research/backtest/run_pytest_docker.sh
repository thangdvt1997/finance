#!/bin/bash
# Chay pytest cua 1 service pattern-* trong container tam tu image da build (ro, khong dung container san xuat). Dung: run_pytest_docker.sh pattern-engine [extra pip]
s=$1; shift
nice -n 19 timeout 900 docker run --rm --cpus 1 --memory 1g -v /root/trading-system/services/$s:/w:ro -w /w --entrypoint sh tradingsys-$s:latest -c "pip install -q --target /tmp/pt pytest pytest-asyncio fakeredis httpx $* 2>&1|grep -i error; PYTHONPATH=/tmp/pt:/w/src:/w python -m pytest -q -p no:cacheprovider tests 2>&1 | tail -25"
