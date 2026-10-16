"""Kiem chung lo hong 'consumer = hostname, khong XAUTOCLAIM': neu 1 instance storage-writer chet (hoac container bi RECREATE
-> hostname moi) khi dang giu message chua ack, message do mac ket trong PEL cua consumer cu, khong ai xu ly.
Mo phong an toan bang container phu qa-sw (cung image/group) bi SIGKILL; sau do khoi phuc moi message that bi ket.
Chay boi run_orphan.sh. Phase: publish | inspect | recover"""
import asyncio
import json
import sys
import time

from qalib import Ctx, Results, mk_event, now, publish_many

PH = sys.argv[1]
N = 4000
R = Results(f"orphan_{PH}")


async def main():
    async with Ctx() as c:
        if PH == "publish":
            base = now().replace(second=0, microsecond=0, hour=0, minute=0)
            from datetime import timedelta
            evs = [mk_event("bar", {"symbol": "QAORPHAN", "tf": "M1", "ts_open": (base - timedelta(days=200) + timedelta(minutes=i)).isoformat(),
                                    "o": 1, "h": 1, "l": 1, "c": 1, "v": 1, "source": "qa"}) for i in range(N)]
            open("/qa/out/orphan_flag", "w").write("1")
            await publish_many(c.r, "md.bars", evs, pipe=100)
            print("published", N)
        elif PH == "inspect":
            for _ in range(60):
                g = [x for x in await c.r.xinfo_groups("md.bars") if x["name"] == "storage-writer"][0]
                if (g.get("lag") or 0) == 0:
                    break
                await asyncio.sleep(1)
            await asyncio.sleep(3)
            rows = await c.db.fetchval("select count(*) from bars where symbol='QAORPHAN' and source='qa'")
            cons = await c.r.xinfo_consumers("md.bars", "storage-writer")
            orphans = [(x["name"], x["pending"], x["idle"]) for x in cons if x["pending"] > 0]
            R.info("consumers", str([(x["name"], x["pending"], x["idle"]) for x in cons]))
            ok = rows == N and not orphans
            R.check("orphan/khong-mat-message-khi-1-consumer-chet", ok,
                    f"DB={rows}/{N}; PEL mo coi={orphans} (consumer da chet giu message chua ack; khong co XAUTOCLAIM)", "high")
            R.metric("db_rows", rows)
        elif PH == "recover":
            tot_q = tot_real = 0
            for st in ("md.bars", "md.quotes", "news.items", "calendar.events", "expert.profiles", "expert.signals", "expert.positions", "account.snapshots", "alerts.out"):
                try:
                    cons = await c.r.xinfo_consumers(st, "storage-writer")
                except Exception:
                    continue
                for cn in cons:
                    if cn["pending"] == 0 or not cn["name"].startswith("qa-sw"):
                        continue
                    while True:
                        pend = await c.r.xpending_range(st, "storage-writer", "-", "+", 500, consumername=cn["name"])
                        if not pend:
                            break
                        ids = [p["message_id"] for p in pend]
                        msgs = await c.r.xclaim(st, "storage-writer", "qa-recover", 0, ids)
                        for mid, f in msgs:
                            e = f.get("e", "")
                            if '"source": "qa"' in e or '"trace_id": "qa"' in e:
                                tot_q += 1
                            else:  # su kien that bi ket -> phat lai (upsert idempotent) de khong mat du lieu
                                await c.r.xadd(st, {"e": e})
                                tot_real += 1
                            await c.r.xack(st, "storage-writer", mid)
                    await c.r.execute_command("XGROUP", "DELCONSUMER", st, "storage-writer", cn["name"])
            await c.r.execute_command("XGROUP", "DELCONSUMER", "md.bars", "storage-writer", "qa-recover")
            print(f"recover: qa={tot_q} real-republished={tot_real}")
    return R.finish()

raise SystemExit(asyncio.run(main()))
