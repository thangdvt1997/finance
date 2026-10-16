#!/bin/sh
# QA-G: chay eg_g_live.py trong container tam (mang tradingsys). Ket qua /tmp/qa_stab_eg_g/out/eg_g_live.json
SRC="$(cd "$(dirname "$0")" && pwd)"; D=/tmp/qa_stab_eg_g
mkdir -p $D/out $D/pip && cp "$SRC/eg_g_live.py" "$SRC/../e2e/qalib.py" $D/
exec env QA_DIR=$D sh "$SRC/../e2e/run_remote.sh" eg_g_live.py
