"""Don sach du lieu test (source='qa', symbol QA*, account qa-*, tag qa, message id da publish).
Chi xoa du lieu do bo test tao ra; khong dung vao du lieu that."""
import asyncio
import json
import os
from collections import defaultdict

from qalib import OUT, Ctx

MARK = 777777.77


async def main():
    async with Ctx() as c:
        db, r = c.db, c.r
        # ---------- Redis: xoa message da publish
        ids = defaultdict(list)
        p = os.path.join(OUT, "published_ids.jsonl")
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                try:
                    st, mid = json.loads(line)
                    ids[st].append(mid)
                except Exception:
                    pass
        tot = 0
        for st, lst in ids.items():
            for i in range(0, len(lst), 1000):
                tot += await r.xdel(st, *lst[i:i + 1000])
        print(f"redis: XDEL {tot} message test tu {len(ids)} stream")
        # dlq + alerts.delivery: xoa muc co dau hieu qa
        for st in ("dlq", "alerts.delivery"):
            try:
                ents = await r.xrange(st, "-", "+")
            except Exception:
                continue
            kill = [i for i, f in ents if any(m in json.dumps(f) for m in ('"trace_id": "qa"', "QA-DLQ", "QA alert", "QA load", "QALOAD", "QACRASH", "qa-load", "QAUSD", "qa-acct", "qa-expert", "QA bad", "qa.invalid"))
                    or '\\"trace_id\\": \\"qa\\"' in json.dumps(f)]
            if kill:
                n = 0
                for i in range(0, len(kill), 1000):
                    n += await r.xdel(st, *kill[i:i + 1000])
                print(f"redis: {st} XDEL {n}/{len(ents)}")
        # alert-service state
        for key in ("alerts:recent", "alerts:digest_buffer"):
            try:
                items = await r.lrange(key, 0, -1)
            except Exception:
                continue
            n = 0
            for it in items:
                if '"title": "QA' in it or "QA alert" in it or "QA bad" in it or "QALOAD" in it:
                    n += await r.lrem(key, 0, it)
            print(f"redis: {key} lrem {n}/{len(items)}")
        async for k in r.scan_iter("alerts:dedupe:qa*"):
            await r.delete(k)
        # ---------- DB
        wins, cur = [], None
        wp = os.path.join(OUT, "windows.json")
        if os.path.exists(wp):
            for line in open(wp):
                j = json.loads(line)
                if "mt_start" in j:
                    cur = j["mt_start"]
                elif "mt_end" in j and cur:
                    wins.append((cur, j["mt_end"]))
                    cur = None
        from datetime import datetime
        stmts = [
            ("bars", "DELETE FROM bars WHERE symbol >= 'QA' AND symbol < 'QB'"),   # khoang symbol (dung chi muc symbol,tf,ts_open); 'OR source' / LIKE quet moi chunk nen, >10 phut khi tai cao
            ("quotes", "DELETE FROM quotes WHERE symbol >= 'QA' AND symbol < 'QB'"),
            ("news_items", "DELETE FROM news_items WHERE source='qa' OR url LIKE 'https://qa.invalid/%'"),
            ("calendar_events", "DELETE FROM calendar_events WHERE source='qa'"),
            ("expert_signals", "DELETE FROM expert_signals WHERE source='qa'"),
            ("expert_positions", "DELETE FROM expert_positions WHERE source='qa'"),
            ("experts", "DELETE FROM experts WHERE source='qa' OR expert_id LIKE 'qa-%'"),
            ("account_snapshots", f"DELETE FROM account_snapshots WHERE account_id LIKE 'qa-%' OR (account_id='demo-mt4-01' AND balance IN ({MARK}, 777777.78))"),
            ("alerts(qa)", "DELETE FROM alerts WHERE title LIKE 'QA %' OR 'qa' = ANY(tags)"),
        ]
        try:  # bars/quotes nen (compression policy): DELETE tren chunk da nen can bo gioi han giai nen
            await db.execute("SET timescaledb.max_tuples_decompressed_per_dml_transaction = 0")
        except Exception as e:
            print('canh bao: khong dat duoc max_tuples_decompressed:', e)
        for name, sql in stmts:
            res = await db.execute(sql)
            print(f"db: {name}: {res}")
        for a, b in wins:  # canh bao do test LIVE sinh ra (trade_allowed / mat heartbeat / ket noi lai / drawdown) trong cua so test + 5 phut
            res = await db.execute("DELETE FROM alerts WHERE ts >= $1::timestamptz AND ts <= $2::timestamptz + interval '5 minutes' AND 'account:demo-mt4-01' = ANY(tags)",
                                   datetime.fromisoformat(a), datetime.fromisoformat(b))
            print(f"db: alerts(security demo-mt4-01 trong cua so {a[11:19]}..{b[11:19]}): {res}")
        # xac minh
        left = {
            "bars": await db.fetchval("select count(*) from bars where symbol >= 'QA' and symbol < 'QB'"),
            "quotes": await db.fetchval("select count(*) from quotes where symbol >= 'QA' and symbol < 'QB'"),
            "news": await db.fetchval("select count(*) from news_items where source='qa'"),
            "calendar": await db.fetchval("select count(*) from calendar_events where source='qa'"),
            "signals": await db.fetchval("select count(*) from expert_signals where source='qa'"),
            "experts": await db.fetchval("select count(*) from experts where source='qa'"),
            "accounts": await db.fetchval("select count(*) from account_snapshots where account_id like 'qa-%' or balance=777777.77"),
            "alerts": await db.fetchval("select count(*) from alerts where title like 'QA %' or 'qa'=any(tags)"),
        }
        print("con lai (phai = 0):", left)
        return 0 if not any(left.values()) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
