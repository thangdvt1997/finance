#!/usr/bin/env python
"""Đẩy N tin thật (JSON-lines từ DB) vào Redis stream news.items, đợi nlp làm giàu xong, in thông lượng + mẫu kết quả.

Dùng trong mạng tạm với redis tạm (KHÔNG chạm Redis thật của hệ thống):
  python loadtest_feed.py --redis redis://nlp-smoke-redis:6379/0 --file /data/news.jsonl --status http://nlp-smoke-svc:8000
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
import urllib.request

from tscommon.bus import Bus
from tscommon.events import make_event


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--redis", required=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--status", default="")
    ap.add_argument("--timeout", type=float, default=900)
    a = ap.parse_args()
    bus = Bus.from_url(a.redis)
    rows = [json.loads(line) for line in open(a.file, encoding="utf-8") if line.strip()]
    t0 = time.time()
    for r in rows:
        await bus.publish("news.items", make_event("news", "loadtest", {
            "url": r["url"], "title": r["title"], "summary": r.get("summary"), "published_at": r.get("published_at"),
            "source": r["source"], "lang": r.get("lang"), "symbols": r.get("symbols") or [], "sentiment": None}))
    print(f"đã đẩy {len(rows)} tin trong {time.time() - t0:.1f}s")
    t1 = time.time()
    last = -1
    while time.time() - t1 < a.timeout:
        n = await bus.r.xlen("news.enriched")
        if n != last:
            last = n
        if n >= len(rows):
            break
        await asyncio.sleep(1)
    dt = time.time() - t1
    n = await bus.r.xlen("news.enriched")
    print(f"enriched={n}/{len(rows)} sau {dt:.1f}s => {n / max(dt, 1e-9):.1f} tin/s")
    pend = await bus.r.xpending("news.items", "nlp")
    print("pending còn lại:", pend["pending"])
    if a.status:
        print(urllib.request.urlopen(a.status + "/status", timeout=5).read().decode())
        for line in urllib.request.urlopen(a.status + "/metrics", timeout=5).read().decode().splitlines():
            if line.startswith(("nlp_items_total", "nlp_errors", "nlp_skipped", "nlp_infer_seconds_sum", "nlp_infer_seconds_count",
                                "nlp_batch_size_sum", "nlp_batch_size_count", "nlp_symbol_sentiment")):
                print(line)
    res = await bus.r.xrange("news.enriched", count=400)
    import random
    random.seed(1)
    for _id, f in random.sample(res, min(8, len(res))):
        p = json.loads(f["e"])["payload"]
        print(f"{p['lang']} {p['label']:8s} {p['sentiment']:+.2f} conf={p['confidence']:.2f} imp={p['importance']:4s} "
              f"{p['symbols']} {p['topics']} | {p['title'][:70]}")
    al = await bus.r.xrange("alerts.out")
    print("alerts phát ra:", len(al))
    for _id, f in al[:5]:
        print("  ", json.loads(f["e"])["payload"]["title"])


if __name__ == "__main__":
    asyncio.run(main())
