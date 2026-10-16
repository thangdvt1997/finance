P="docker exec tradingsys-timescaledb-1 psql -U ts -d ts -At -c"
echo "[account_snapshots]"; $P "select account_id,platform,count(*),max(ts) from account_snapshots group by 1,2"
echo "[quotes]"; $P "select source,symbol,count(*),max(ts) from quotes where source like 'mt%' group by 1,2"
echo "[bars]"; $P "select source,symbol,tf,count(*),max(ts_open) from bars where source like 'mt%' group by 1,2,3 order by 1,3"
echo "[redis]"; for s in account.snapshots md.quotes md.bars alerts.out; do printf "%s=" $s; REDISCLI_AUTH=$(grep -E "^REDIS_ADMIN_PASSWORD=" /root/trading-system/infra/.env | cut -d= -f2-) docker exec -e REDISCLI_AUTH tradingsys-redis-1 redis-cli --no-auth-warning --user ts_admin XLEN $s; done
echo "[alerts mt]"; $P "select ts,level,title from alerts where tags::text ilike '%mt%' or title ilike '%demo-mt%' order by id desc limit 5"
