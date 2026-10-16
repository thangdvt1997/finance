#!/bin/sh
# Chay pattern_research.bt_artifacts trong container pe-research (ma ro, du lieu rw). Dung: sh infra/ops/bt_art.sh ledger|charts|examples|golden|package
R=/root/trading-system
mkdir -p /tmp/bt_ref && [ -f /tmp/bt_ref/image1.png ] || unzip -o -q "$R/plan1/Lệnh Sell.docx" 'word/media/*' -d /tmp/bt_ref_x && cp /tmp/bt_ref_x/word/media/*.png /tmp/bt_ref/
exec docker run --rm --user 1005:1006 -e HOME=/tmp -e MPLCONFIGDIR=/tmp --cpus ${CPUS:-12} \
  -v $R/services:/src/services:ro -v $R/data/research/patterns:/data -v $R/docs/research/pattern_sell:/repo/docs/research/pattern_sell \
  -v /tmp/bt_ref:/ref:ro -v $R/services/pattern-scan/examples:/ex:ro \
  -e PATTERN_DATA=/data -e PATTERN_SPEC_DIR=/src/services/pattern-engine/spec \
  -e PYTHONPATH=/src/services/pattern-engine/src:/src/services/pattern-research:/src/services/pattern-render/src \
  pe-research python -m pattern_research.bt_artifacts "$@"
