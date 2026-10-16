#!/bin/sh
# Chạy A/B trên VPS sau `ab_stack.sh up`: sh /root/trading-system/infra/perf/ab_run.sh   (nền: nohup ... &). Kết quả /root/qa-e2e/out/bench_ab_*.json, cờ xong: out/ab_done
O=overview,bars_h1,bars_m1,symbols,quotes,news,calendar,an_overview,intel_strength,intel_heatmap,vn_overview,risk,mixed
H=overview,quotes,bars_m1
R=/root/trading-system/infra/perf/run_bench.sh
OUT=/root/qa-e2e/out
rm -f $OUT/ab_done $OUT/bench_ab_*.json
for v in before after; do
  docker restart perf-gw-$v >/dev/null; sleep 40
  sh $R ab_gw_$v MODE=gw BASE=http://perf-gw-$v:8000 ONLY=$O VUS=30 DUR=10s GAP=15 > $OUT/ab_gw_$v.log 2>&1
  sleep 60
  sh $R ab_web_$v BASE=http://perf-web-$v:8080 ONLY=$O,static_index,static_js VUS=30 DUR=10s GAP=15 > $OUT/ab_web_$v.log 2>&1
  sleep 60
  sh $R ab_stress_$v MODE=gw BASE=http://perf-gw-$v:8000 ONLY=$H VUS=200 DUR=12s GAP=30 > $OUT/ab_stress_$v.log 2>&1
done
echo done > $OUT/ab_done
