#!/bin/sh
# QA nhom B: kiem DB (chi doc): quotes song, bars lien tuc, lech nguon. Chay: sh tests/qa/b_db_probe.sh
cd /root/trading-system/infra && set -a && . ./.env && set +a
Q(){ docker exec tradingsys-timescaledb-1 psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "$1"; }
echo "ma co quote 5 phut qua:"; Q "select count(distinct symbol) from quotes where ts>now()-interval '5 min'"
echo "ma im > 2h (ten, lan cuoi):"; Q "select s||' '||m from (select symbol s,max(ts) m from quotes group by 1) t where m<now()-interval '2 hours' order by m" | head -50
echo "lo hong M1 > 3 phut / 48h, canon, 6 ma chinh:"
for s in EURUSD GBPUSD USDJPY XAUUSD US500 DE40; do Q "with x as (select ts_open, lead(ts_open) over(order by ts_open) n from bars where symbol='$s' and tf='M1' and source like 'canon:%' and ts_open>now()-interval '48 hours') select '$s '||ts_open||' -> '||n from x where n-ts_open>interval '3 min' order by 1"; done
