"""CLI replay DLQ an toàn: `python -m storage_writer.dlq_replay [--stream S] [--reason-prefix P] [--since ISO|ms] [--limit N] [--apply]`.

Mặc định DRY-RUN (chỉ liệt kê). Với --apply: XADD lại `e` gốc vào stream gốc (writer sẽ xử lý lại, upsert idempotent) rồi XDEL bản trong dlq.
Chỉ replay các lý do "tạm thời" theo mặc định (db-*, max_deliveries*); lý do dữ liệu hỏng (decode/mapping) cần --include-bad.
Môi trường: REDIS_URL (trong container storage-writer đã có). Ví dụ:
  docker exec tradingsys-storage-writer-1 python -m storage_writer.dlq_replay --reason-prefix db --since 2026-10-11T00:00:00Z
"""
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime, timezone

import redis.asyncio as aioredis

from .mapping import MAPPERS

SAFE_PREFIXES = ("db", "max_deliveries")


def _ms(v: str) -> int:
    if v.isdigit():
        return int(v)
    return int(datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp() * 1000)


async def run(args) -> int:
    r = aioredis.from_url(args.redis_url, decode_responses=True)
    start = f"{_ms(args.since)}-0" if args.since else "-"
    n_sel = n_done = 0
    cursor = start
    while True:
        batch = await r.xrange("dlq", min=cursor if cursor == start else f"({cursor}", max="+", count=200)
        if not batch:
            break
        for mid, f in batch:
            cursor = mid
            reason = f.get("reason", "")
            if args.stream and f.get("stream") != args.stream:
                continue
            if args.reason_prefix and not reason.startswith(args.reason_prefix):
                continue
            if not args.reason_prefix and not args.include_bad and not reason.startswith(SAFE_PREFIXES):
                continue
            if f.get("stream") not in MAPPERS or not f.get("e"):
                continue
            n_sel += 1
            print(f"{'REPLAY' if args.apply else 'would-replay'} {mid} {f['stream']} :: {reason[:100]}")
            if args.apply:
                await r.xadd(f["stream"], {"e": f["e"]})
                await r.xdel("dlq", mid)
                n_done += 1
            if args.limit and n_sel >= args.limit:
                break
        if args.limit and n_sel >= args.limit:
            break
    print(f"selected={n_sel} replayed={n_done} (dry-run={not args.apply})")
    await r.aclose()
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stream"), ap.add_argument("--reason-prefix"), ap.add_argument("--since")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--include-bad", action="store_true", help="cả lý do decode/mapping/invalid (thường replay vẫn lỗi)")
    ap.add_argument("--apply", action="store_true", help="thực hiện (mặc định chỉ dry-run)")
    ap.add_argument("--redis-url", default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    raise SystemExit(asyncio.run(run(ap.parse_args())))


if __name__ == "__main__":
    main()
