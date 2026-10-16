#!/bin/bash
# pytest cua 1 service trong container tam (image da build, mount ro, ghi /tmp). Dung: run_svc_tests.sh ai-trading|briefing|nlp|data-keeper [test-path]
s=$1; shift
nice -n 19 timeout 900 docker run --rm --cpus 1 --memory 1g -v /root/trading-system/services:/r/services:ro -v /root/trading-system/docs:/docs:ro -e AI_CLASS_DIR=/tmp/cls \
 --entrypoint sh tradingsys-$s:latest -c "cp -r /r/services/$s /tmp/w; pip install -q --target /tmp/pt pytest httpx pytest-asyncio fakeredis 2>&1|grep -i error; cd /tmp/w; PYTHONPATH=/tmp/pt:/tmp/w/src:/tmp/w python -m pytest -q -p no:cacheprovider ${@:-tests} 2>&1|tail -12"
# nlp: venv khong co pip -> cai pytest/fakeredis/pytest-asyncio len host: pip install --target $D pytest fakeredis pytest-asyncio; roi
#   docker run --rm -v $D:/pt:ro -v /root/trading-system/services:/r/services:ro --entrypoint sh tradingsys-nlp:latest -c "cp -r /r/services/nlp /tmp/w; cd /tmp/w; PYTHONPATH=/pt:/tmp/w/src:/tmp/w python -m pytest -q -p no:cacheprovider tests"
