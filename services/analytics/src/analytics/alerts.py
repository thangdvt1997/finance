"""Cảnh báo ĐIỀU KIỆN (bật/tắt trong YAML). Không có tín hiệu mua/bán — chỉ nêu điều kiện kỹ thuật vừa xảy ra.

Phát hiện theo cạnh (so 2 nến gần nhất) nên không cần lưu trạng thái; `dedupe_key` chứa mốc nến nên mỗi điều kiện
chỉ báo 1 lần/nến, kể cả khi service khởi động lại; alert-service dedupe thêm theo khoá này.
"""
from __future__ import annotations

from .engine import Analysis
from .indicators import last, percentile_rank
from .states import DISCLAIMER


def _alert(level: str, title: str, body: str, tags: list[str], key: str) -> dict:
    return {"level": level, "title": title, "body": f"{body}\n{DISCLAIMER}", "tags": ["analytics", *tags], "dedupe_key": key}


def _tf_ok(cfg: dict, tf: str) -> bool:
    tfs = cfg.get("tfs")
    return not tfs or tf in tfs


def bar_alerts(a: Analysis, cfg: dict) -> list[dict]:
    out: list[dict] = []
    if len(a.df) < 3 or not cfg.get("enabled", True):
        return out
    s, tf = a.symbol, a.tf
    bar = a.df.index[-1].strftime("%Y%m%dT%H%M")
    ind = a.ind
    base = f"an:{{rule}}:{s}:{tf}"

    r = cfg.get("rsi_cross", {})
    if r.get("enabled") and _tf_ok(r, tf):
        cur, prev = last(ind["rsi"]), last(ind["rsi"], -2)
        up, lo = float(r.get("upper", 70)), float(r.get("lower", 30))
        if cur is not None and prev is not None:
            ev = None
            if prev < up <= cur:
                ev = ("up_over", f"RSI(14) cắt lên {up:g} (vào vùng quá mua)")
            elif prev >= up > cur:
                ev = ("up_under", f"RSI(14) cắt xuống dưới {up:g} (rời vùng quá mua)")
            elif prev > lo >= cur:
                ev = ("lo_under", f"RSI(14) cắt xuống {lo:g} (vào vùng quá bán)")
            elif prev <= lo < cur:
                ev = ("lo_over", f"RSI(14) cắt lên trên {lo:g} (rời vùng quá bán)")
            if ev:
                out.append(_alert("info", f"{s} {tf}: {ev[1]}", f"RSI trước {prev:.1f} → hiện {cur:.1f} (nến {a.df.index[-1]:%Y-%m-%d %H:%M} UTC).",
                                  ["rsi_cross", s, tf], f"{base.format(rule='rsi')}:{ev[0]}:{bar}"))

    e = cfg.get("ema200_touch", {})
    if e.get("enabled") and _tf_ok(e, tf):
        e2, e1 = last(ind["ema200"]), last(ind["ema200"], -2)
        if e2 is not None and e1 is not None:
            touch_now = a.df["l"].iloc[-1] <= e2 <= a.df["h"].iloc[-1]
            touch_prev = a.df["l"].iloc[-2] <= e1 <= a.df["h"].iloc[-2]
            if touch_now and not touch_prev:
                out.append(_alert("info", f"{s} {tf}: giá chạm EMA200",
                                  f"Nến hiện tại có biên độ [{a.df['l'].iloc[-1]:.6g}; {a.df['h'].iloc[-1]:.6g}] chứa EMA200 = {e2:.6g}.",
                                  ["ema200_touch", s, tf], f"{base.format(rule='ema200')}:{bar}"))

    b = cfg.get("range_breakout", {})
    if b.get("enabled") and _tf_ok(b, tf):
        n = int(b.get("days", 20))
        if len(a.df) > n + 1:
            hi = float(a.df["h"].iloc[-n - 1:-1].max())
            lo = float(a.df["l"].iloc[-n - 1:-1].min())
            c = float(a.df["c"].iloc[-1])
            if c > hi:
                out.append(_alert("warn", f"{s} {tf}: đóng cửa vượt đỉnh {n} nến", f"Đóng {c:.6g} > đỉnh {n} nến trước {hi:.6g}.",
                                  ["range_breakout", s, tf], f"{base.format(rule='brk')}:hi{n}:{bar}"))
            elif c < lo:
                out.append(_alert("warn", f"{s} {tf}: đóng cửa thủng đáy {n} nến", f"Đóng {c:.6g} < đáy {n} nến trước {lo:.6g}.",
                                  ["range_breakout", s, tf], f"{base.format(rule='brk')}:lo{n}:{bar}"))

    v = cfg.get("volatility_spike", {})
    if v.get("enabled") and _tf_ok(v, tf):
        thr = float(v.get("atr_percentile", 95))
        ap = ind["atr_pct"]
        cur = percentile_rank(ap, last(ap))
        prev = percentile_rank(ap[:-1], last(ap, -2))
        if cur is not None and prev is not None and prev < thr <= cur:
            out.append(_alert("warn", f"{s} {tf}: biến động tăng đột biến",
                              f"ATR% = {last(ap):.3f}% ở phân vị {cur:.0f} của lịch sử (trước đó {prev:.0f}, ngưỡng {thr:g}).",
                              ["volatility_spike", s, tf], f"{base.format(rule='vol')}:{bar}"))
    return out


def correlation_alerts(flips: list[dict], cfg: dict, tf: str, as_of: str) -> list[dict]:
    c = cfg.get("correlation_flip", {})
    if not cfg.get("enabled", True) or not c.get("enabled"):
        return []
    day = as_of[:10].replace("-", "")
    return [_alert("warn", f"Tương quan {f['a']}/{f['b']} đổi chiều bất thường",
                   f"Tương quan {tf} 30 ngày: {f['prev']:+.2f} (cửa sổ trước) → {f['now']:+.2f} (hiện tại), lệch {f['delta']:+.2f}.",
                   ["correlation_flip", f["a"], f["b"]], f"an:corr:{f['a']}:{f['b']}:{day}") for f in flips]
