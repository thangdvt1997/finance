#!/bin/bash
# Chay test AI tat dinh trong container tam (image ai-trading), mount ro. Dung: run_ai.sh [pytest-args]
nice -n 19 timeout 600 docker run --rm --cpus 1 --memory 1g -v /root/trading-system:/r:ro -w /r --entrypoint sh tradingsys-ai-trading:latest -c \
 "pip install -q --target /tmp/pt pytest 2>&1|grep -i error; PYTHONPATH=/tmp/pt:/r/services/ai-trading/src python -m pytest -q -p no:cacheprovider -s tests/qa/research/ai/test_ai_core.py tests/qa/research/ai/test_intent_heldout.py $* 2>&1 | tail -60"
# Bo test san co cua service ai-trading (cung container tam, ghi vao /tmp):
#   docker run --rm -v /root/trading-system/services/ai-trading:/s:ro -e AI_CLASS_DIR=/tmp/cls --entrypoint sh tradingsys-ai-trading:latest -c "cp -r /s /tmp/w; cd /tmp/w; pip install -q --target /tmp/pt pytest httpx pytest-asyncio fakeredis; PYTHONPATH=/tmp/pt:/tmp/w/src python -m pytest -q -p no:cacheprovider tests"
