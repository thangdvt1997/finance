#!/bin/sh
# Stress 200 VU cho ngăn xếp SAU (bản cuối). Cờ xong: out/ab3_done
OUT=/root/qa-e2e/out; P=/root/trading-system/infra/perf
rm -f $OUT/ab3_done; sleep 45
sh $P/run_bench.sh ab3_stress_after MODE=gw BASE=http://perf-gw-after:8000 ONLY=overview,quotes,bars_m1,bars_h1,news,calendar,intel_heatmap VUS=200 DUR=12s GAP=25 > $OUT/ab3_stress_after.log 2>&1
echo done > $OUT/ab3_done
