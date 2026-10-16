"""Backfill LICH SU D1 qua market-collector (duong chinh thong: provider -> quality -> md.bars -> storage-writer).
Chay TRONG container market-collector (co BACKFILL_TOKEN trong env):
  docker compose -p tradingsys --env-file .env exec -T market-collector python - yahoo_daily:1990-01-01:SYMS... < infra/ops/backfill_hist.py
Dung:  python - <provider>:<start YYYY-MM-DD>:<sym1,sym2,...>  [...]      (moi nhom 1 doi so)
Cua so > 10 nam duoc tu chia (gioi han cua /backfill). Tuan tu, cho tung job xong (khong tao tai qua nang)."""
import json, os, sys, time, urllib.request
from datetime import datetime, timedelta, timezone

TOK = os.environ["BACKFILL_TOKEN"]
BASE = "http://localhost:8000"


def call(path, body=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-Backfill-Token": TOK, "content-type": "application/json",
                                          **({"X-Internal-Token": os.environ["INTERNAL_TOKEN"]} if os.environ.get("INTERNAL_TOKEN") else {})})
    return json.load(urllib.request.urlopen(req, timeout=60))


def run(provider, sym, start, end):
    jid = call("/backfill", {"provider": provider, "symbol": sym, "start": start.isoformat(), "end": end.isoformat()})["job_id"]
    while True:
        time.sleep(3)
        j = call("/status")["jobs"][jid]
        if j["state"] != "running":
            return j


for arg in sys.argv[1:]:
    provider, start_s, syms = arg.split(":", 2)
    start = datetime.fromisoformat(start_s).replace(tzinfo=timezone.utc)
    for sym in syms.split(","):
        t0, tot, cur = time.time(), 0, start
        end_all = datetime.now(timezone.utc)
        while cur < end_all:
            nxt = min(cur + timedelta(days=3600), end_all)
            j = run(provider, sym, cur, nxt)
            if j["state"] != "done":
                print(f"FAIL {provider} {sym} {cur.date()}: {j}", flush=True)
                break
            tot += j.get("bars", 0)
            cur = nxt
        print(f"{provider} {sym} bars={tot} {time.time()-t0:.0f}s", flush=True)
