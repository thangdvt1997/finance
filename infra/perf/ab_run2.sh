#!/bin/sh
# Vòng đo bổ sung sau khi sửa SWR-khi-vô-hiệu: stress 200 VU (after) + thời gian tải trang A/B. Cờ xong: out/ab2_done
OUT=/root/qa-e2e/out; P=/root/trading-system/infra/perf
rm -f $OUT/ab2_done
sleep 45
sh $P/run_bench.sh ab2_stress_after MODE=gw BASE=http://perf-gw-after:8000 ONLY=overview,quotes,bars_m1,bars_h1 VUS=200 DUR=12s GAP=25 > $OUT/ab2_stress_after.log 2>&1
sleep 20
for v in before after; do
  sh $P/run_pageload.sh ab2_page_$v BASE=http://perf-web-$v:8080 N=4 > $OUT/ab2_page_$v.log 2>&1
done
echo done > $OUT/ab2_done
