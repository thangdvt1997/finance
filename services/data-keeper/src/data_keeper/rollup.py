"""Vá lỗ khung cao (M5/M15/H1) của chuỗi canon từ M1 đã lưu trong bars.

Nguyên nhân gốc (đo 2026-10-16): mt-bridge gộp M5/M15/H1 từ M1 trong BỘ NHỚ (feed.py). Mỗi lần mt-bridge khởi động lại (deploy),
bucket đang dựng mất và bucket dở dang không đủ điều kiện phát -> mất đúng 1 nến M5/M15/H1 quanh thời điểm restart,
nên last_bar M15 kẹt tới 30-45 phút => dk.coverage SLOW hàng loạt. M1 thì đã được lưu ngay nên gộp lại từ DB là chính xác.

Ghi: INSERT ... ON CONFLICT DO NOTHING (không đè nến feed đã phát), chỉ source canon:*, chỉ bucket ĐÃ ĐÓNG > GRACE_S,
cửa sổ ngắn (WINDOW_S) nên rẻ; chạy TRƯỚC kiểm kê mỗi chu kỳ. Không đụng đường giá (không đọc/ghi quotes, dừng khi guard xấu).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from prometheus_client import Counter

log = logging.getLogger("data_keeper.rollup")
ROLLUP_TFS = {"M5": 300, "M15": 900, "H1": 3600}
GRACE_S = 180          # bucket phải đóng > 3 phút (M1 cuối kịp về canon)
WINDOW_S = 4 * 3600    # chỉ vá 4 giờ gần nhất (restart gần đây); lỗ cũ hơn do backfill/histload

C_ROLL = Counter("dk_rollup_bars_total", "So nen khung cao duoc va tu M1 canon", ["tf"])

SQL = """
INSERT INTO bars(symbol,tf,ts_open,o,h,l,c,v,source)
SELECT symbol, $1::text, bucket, (array_agg(o ORDER BY ts_open))[1], max(h), min(l), (array_agg(c ORDER BY ts_open DESC))[1],
       coalesce(sum(v),0), source
FROM (SELECT symbol, source, ts_open, o, h, l, c, v, to_timestamp(floor(extract(epoch FROM ts_open)/$2::int)*$2::int) AS bucket
      FROM bars WHERE tf='M1' AND source LIKE 'canon:%' AND ts_open >= to_timestamp($3::bigint) AND ts_open < to_timestamp($4::bigint)) t
GROUP BY symbol, source, bucket
HAVING count(*) >= $2::int/60   -- du M1 moi tinh (feed bo bucket thieu M1 sau phien moi/EA offline)
ON CONFLICT (symbol,tf,ts_open,source) DO NOTHING
"""


def window(tf: str, now: float) -> tuple[int, int]:
    """[lo, hi) epoch: hi = moc khung gan nhat <= now-GRACE_S (bucket dong hoan toan), lo = hi - WINDOW_S can theo khung."""
    sec = ROLLUP_TFS[tf]
    hi = int(now - GRACE_S) // sec * sec
    lo = (hi - WINDOW_S) // sec * sec
    return lo, hi


async def rollup_cycle(ctx, matrix: dict | None = None) -> dict:
    guard = getattr(ctx, "guard", None)
    if guard is not None and hasattr(guard, "ok") and not guard.ok():
        return {"skipped": "guard"}
    db = ctx.db
    if db is None or (getattr(db, "rw", None) is None):
        return {"skipped": "no_rw"}
    now = time.time()
    out: dict[str, int] = {}
    for tf, sec in ROLLUP_TFS.items():
        lo, hi = window(tf, now)
        res = await db.execute(SQL, tf, sec, lo, hi)
        n = int(str(res).split()[-1]) if res else 0
        out[tf] = n
        if n:
            C_ROLL.labels(tf).inc(n)
    if any(out.values()):
        log.info("rollup va nen khung cao tu M1: %s", out)
    return out
