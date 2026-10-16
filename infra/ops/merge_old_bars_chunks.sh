#!/usr/bin/env bash
# Gộp chunk tuần cũ của hypertable bars thành chunk theo năm (giảm planning time: 2913 chunk -> ~vài trăm).
# Dùng: merge_old_bars_chunks.sh <năm_từ> <năm_đến>   (vd 1970 2017). An toàn: mỗi năm 1 lệnh riêng, lock_timeout 10s, bỏ qua nếu bận.
set -u
PG=${PG:-tradingsys-timescaledb-1}
Y0=${1:?năm từ}; Y1=${2:?năm đến}
q() { docker exec -i -e PGOPTIONS='-c lock_timeout=3s -c statement_timeout=0' "$PG" sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d ts -At' <<<"$1"; }
for y in $(seq "$Y0" "$Y1"); do
  n=$(q "select count(*) from timescaledb_information.chunks where hypertable_name='bars' and range_start>='$y-01-01' and range_start<'$((y+1))-01-01'")
  [ "${n:-0}" -le 1 ] && continue
  s=$(date +%s)
  L=$(q "select string_agg(quote_literal(chunk_schema||'.'||chunk_name),',' order by range_start) from timescaledb_information.chunks where hypertable_name='bars' and range_start>='$y-01-01' and range_start<'$((y+1))-01-01'")
  c0=$(q "select count(*) from bars where ts_open>='$y-01-01' and ts_open<'$((y+1))-01-01'")
  r=FAIL
  for try in 1 2 3 4 5 6; do   # lock_timeout ngắn (3s) để không chặn đọc; thử lại khi có truy vấn quét dài giữ khoá
    q "call merge_chunks(ARRAY[$L]::regclass[]);" >/dev/null 2>&1 && { r=ok; break; }; sleep 20
  done
  c1=$(q "select count(*) from bars where ts_open>='$y-01-01' and ts_open<'$((y+1))-01-01'")
  [ "$c0" = "$c1" ] || r="$r ROWS_MISMATCH($c0/$c1)"
  echo "$y chunks=$n $r $(( $(date +%s)-s ))s"
done
