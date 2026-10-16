"""Bốn kịch bản Sell (KB-1..KB-4) dưới dạng máy trạng thái trên chuỗi swing ZigZag-ATR.

Mỗi kịch bản có 2 phần, cả hai CHỈ dùng nến đã đóng:
  scan(ctx)  : cấu trúc tại nến i -> danh sách Setup (forming | armed) kèm checklist bước.
  check(...) : tại nến i+1 (vừa đóng) so với Setup của nến i -> triggered | invalid | tiếp tục.
Tham số lấy từ spec/*.yaml (đã nạp thành dict P). Mọi ngưỡng chuẩn hoá theo ATR / độ dài sóng.
"""
from __future__ import annotations

from .common import Ctx, Setup, all_leads, best_lead, bear_engulf, closeness, score_of, small_cluster, step, suggest_levels
from .zigzag import Pivot


def _ts(c: Ctx, p: Pivot) -> str:
    return c.s.ts[p.i].strftime("%Y%m%dT%H%M")


def _pt(c: Ctx, i: int, price: float, label: str = "") -> dict:
    """Toạ độ 1 điểm cấu trúc (chỉ để vẽ ảnh/biểu đồ; KHÔNG ảnh hưởng logic phát hiện). i <= nến hiện tại."""
    return {"label": label, "t": c.s.ts[i].isoformat(), "p": round(float(price), 6)}


class Pattern:
    id = "KB-0"
    n_steps = 6

    def __init__(self, spec: dict):
        self.spec = spec
        self.P = spec["params"]
        self.labels = {int(k): v for k, v in spec["steps"].items()}

    def st(self, sid: int, ok: bool, detail: str = "", q: float | None = None) -> dict:
        return step(sid, self.labels[sid], ok, detail, q)

    def scan(self, c: Ctx) -> list[Setup]:  # pragma: no cover - abstract
        raise NotImplementedError

    def check(self, c: Ctx, st: Setup, i: int):  # pragma: no cover - abstract
        raise NotImplementedError

    def _setup(self, c: Ctx, key: str, steps: list[dict], pre_steps: int, anchor_i: int, last_i: int, levels: dict, meta: dict,
               points: list[dict] | None = None):
        """pre_steps = số bước cấu trúc (không tính bước kích hoạt cuối). forming nếu 2 bước đầu ok, armed nếu mọi bước cấu trúc ok."""
        done = [s["ok"] for s in steps[:pre_steps]]
        if not (done[0] and done[1]):
            return None
        state = "armed" if all(done) else "forming"
        steps = steps + [self.st(self.n_steps, False, "chờ nến kích hoạt")]
        return Setup(self.id, key, state, steps, score_of(steps, self.n_steps), levels, meta, anchor_i, last_i, points or [])

    def _final(self, st: Setup, i: int, c: Ctx, quality: float, detail: str, top: float, extra: dict | None = None) -> dict:
        steps = [dict(s) for s in st.steps[:-1]] + [self.st(self.n_steps, True, detail, quality)]
        return {"steps": steps, "score": score_of(steps, self.n_steps),
                "levels": {**st.levels, **suggest_levels(c.s, i, top, self.P, extra)}}


# ======================================================================================= KB-2 (nêm / tam giác)
class KB2(Pattern):
    id = "KB-2"

    def scan(self, c: Ctx) -> list[Setup]:
        P, pv, s, out = self.P, c.pv, c.s, []
        n = len(pv)
        for k in range(max(0, n - int(P["max_pivots_back"])), n - 1):
            l1, h2 = pv[k], pv[k + 1]
            if l1.is_high or not h2.is_high:
                continue
            lead = best_lead(c, k, P)
            if not lead:
                continue
            h0 = lead["h0"]
            if c.i - h2.i > P["max_consol_bars"] or h2.price >= h0.price:
                continue
            atr = s.atr[c.i]
            retr = (h2.price - l1.price) / lead["height"]
            fine = c.fine if c.fine is not None else pv
            rest = [p for p in fine if p.i > h2.i]          # chi tiết tích luỹ lấy từ thang MỊN nhất
            highs = [h2] + [p for p in rest if p.is_high]
            lows = [p for p in rest if not p.is_high]
            env = P["envelope_tol_atr"] * atr
            # Cạnh nêm = đường nối ĐỈNH ĐẦU–ĐỈNH CUỐI và ĐÁY ĐẦU–ĐÁY CUỐI (cách người vẽ nối các điểm chạm); các điểm giữa chỉ cần nằm trong ±env.
            fh = fl = None
            hi_ok = lo_ok = ok5 = False
            ratio = None
            if len(highs) >= P["min_highs"] and highs[-1].i > highs[0].i:
                sl_ = (highs[-1].price - highs[0].price) / (highs[-1].i - highs[0].i)
                fh = (sl_, highs[0].price, highs[0].i)
                hi_ok = (sl_ * (highs[-1].i - highs[0].i) <= -P["min_drop_atr"] * atr
                         and all(p.price <= highs[0].price + sl_ * (p.i - highs[0].i) + env for p in highs))
            if len(lows) >= P["min_lows"] and lows[-1].i > lows[0].i:
                sl_ = (lows[-1].price - lows[0].price) / (lows[-1].i - lows[0].i)
                fl = (sl_, lows[0].price, lows[0].i)
                lo_ok = (sl_ * (lows[-1].i - lows[0].i) >= P["min_rise_atr"] * atr
                         and all(p.price >= lows[0].price + sl_ * (p.i - lows[0].i) - env for p in lows)
                         and lows[0].price >= l1.price - env)
            up = lambda x: fh[1] + fh[0] * (x - fh[2]) if fh else None  # noqa: E731
            dn = lambda x: fl[1] + fl[0] * (x - fl[2]) if fl else None  # noqa: E731
            if hi_ok and lo_ok:
                x0 = highs[0].i
                w0 = up(x0) - dn(x0)
                w1 = up(c.i) - dn(c.i)
                ratio = w1 / w0 if w0 > 0 else None
                ok5 = ratio is not None and 0 < ratio <= P["contraction_max"]
            steps = [
                self.st(1, True, f"sóng dẫn {lead['hn']:.1f} ATR, {lead['longred']} nến đỏ dài, xanh {lead['green']:.0%}"),
                self.st(2, P["retr_min"] <= retr <= P["retr_max"], f"hồi {retr:.0%} sóng (1)", closeness(retr, 0.5, 0.5)),
                self.st(3, hi_ok, f"{len(highs)} đỉnh thấp dần" if hi_ok else f"{len(highs)} đỉnh"),
                self.st(4, lo_ok, f"{len(lows)} đáy cao dần" if lo_ok else f"{len(lows)} đáy"),
                self.st(5, ok5, "co hẹp x%.2f" % ratio if ratio is not None else "chưa đủ đỉnh/đáy",
                        closeness(ratio if ratio is not None else 9, 0.5, 1.0)),
            ]
            meta = {"h0": h0.price, "l1": l1.price, "h2": h2.price, "h2_i": h2.i, "hi_last": highs[-1].price,
                    "lower": fl, "last_low": lows[-1].price if lows else None}
            lv = {"resistance": up(c.i) if fh else None, "support": dn(c.i) if fl else None,
                  "wave_high": h0.price, "wave_low": l1.price}
            lv = {a: b for a, b in lv.items() if b is not None}
            pts = [_pt(c, h0.i, h0.price), _pt(c, l1.i, l1.price, "(1)"), _pt(c, h2.i, h2.price, "(2)")]
            su = self._setup(c, f"KB-2:{_ts(c, l1)}:{_ts(c, h2)}", steps, 5, l1.i, c.i, lv, meta, pts)
            if su:
                out.append(su)
        return out

    def check(self, c: Ctx, st: Setup, i: int):
        P, s, m = self.P, c.s, st.meta
        atr = s.atr_ref(i)
        if s.c[i] > m["h2"] + P["invalid_above_atr"] * atr:
            return "invalid", {"reason": "giá đóng cửa vượt đỉnh hồi (2)"}
        if i - m["h2_i"] > P["max_consol_bars"]:
            return "invalid", {"reason": "quá hạn tích luỹ"}
        if st.state != "armed" or not m["lower"]:
            return None
        lw = m["lower"]
        sup = lw[1] + lw[0] * (i - lw[2])
        ok, info = bear_engulf(s, i, P)
        if ok and s.c[i] < sup:
            q = min(1.0, info["body_atr"] / (2 * P["trigger_body_atr"]) + 0.5)
            return "triggered", self._final(st, i, c, q, f"nhấn chìm giảm thân {info['body_atr']} ATR, đóng dưới cạnh dưới {sup:.2f}",
                                              m["hi_last"], {"support": sup, "prev_low": m["l1"]})
        if s.c[i] < sup - P["break_no_trigger_atr"] * atr:
            return "invalid", {"reason": "phá cạnh dưới nhưng không có nến nhấn chìm"}
        return None


# ======================================================================================= KB-1
class KB1(Pattern):
    id = "KB-1"

    def scan(self, c: Ctx) -> list[Setup]:
        P, pv, s, out = self.P, c.pv, c.s, []
        n = len(pv)
        for k in range(max(0, n - int(P["max_pivots_back"])), n - 3):
            l1, h2, l3, h4 = pv[k], pv[k + 1], pv[k + 2], pv[k + 3]
            if l1.is_high or not (h2.is_high and not l3.is_high and h4.is_high):
                continue
            lead = best_lead(c, k, P)
            if not lead:
                continue
            h0 = lead["h0"]
            if c.i - h4.i > P["max_after_h4_bars"] or h4.price >= h0.price:
                continue
            atr = s.atr[c.i]
            w2 = h2.price - l1.price
            w3 = h2.price - l3.price
            retr = w2 / lead["height"]
            ratio3 = w3 / w2 if w2 > 0 else 0
            over = (h4.price - h2.price) / w3 if w3 > 0 else 9
            a5 = h4.i + 1
            l45 = h5 = None
            side_ok = False
            if c.i - a5 >= 3:
                j = min(range(a5, c.i + 1), key=lambda t: s.l[t])      # đáy giữa (4)-(5): thấp nhất kể từ đỉnh (4)
                if j < c.i:
                    l45 = (j, s.l[j])
                    jh = max(range(j + 1, c.i + 1), key=lambda t: s.h[t])
                    h5 = (jh, s.h[jh])                                   # đỉnh thứ 2: cao nhất sau đáy giữa
                    depth = min(h4.price, h5[1]) - l45[1]
                    drop = h4.price - h5[1]
                    side_ok = (drop >= P["min_drop_atr"] * atr and depth >= P["pullback_min_atr"] * atr
                               and l45[1] >= l3.price - P["pivot_tol_atr"] * atr)
            steps = [
                self.st(1, True, f"sóng dẫn {lead['hn']:.1f} ATR, {lead['longred']} nến đỏ dài, xanh {lead['green']:.0%}"),
                self.st(2, P["retr_min"] <= retr <= P["retr_max"], f"hồi {retr:.0%} sóng (1)", closeness(retr, 0.35, 0.5)),
                self.st(3, abs(ratio3 - 1) <= P["equal_tol"], f"sóng (3)/(2) = {ratio3:.2f}", closeness(ratio3, 1.0, P["equal_tol"] * 2)),
                self.st(4, 0 < over <= P["overshoot_max"], f"vượt đỉnh (2) {over:.0%} sóng (3)", closeness(over, 0.12, P["overshoot_max"] * 1.5)),
                self.st(5, side_ok, "2 đỉnh giảm dần" if side_ok else "chưa có đỉnh thứ 2 thấp hơn"),
            ]
            meta = {"h0": h0.price, "h4": h4.price, "h4_i": h4.i, "h4_conf": h4.conf_i >= 0, "h5": h5[1] if h5 else None, "h5_i": h5[0] if h5 else None,
                    "l45": l45[1] if l45 else None, "l3": l3.price, "l1": l1.price, "h2": h2.price}
            lv = {"wave_high": h0.price, "wave_low": l1.price, "high_4": h4.price, "low_3": l3.price}
            if h5:
                lv["high_5"] = h5[1]
            pts = [_pt(c, h0.i, h0.price), _pt(c, l1.i, l1.price, "(1)"), _pt(c, h2.i, h2.price, "(2)"),
                   _pt(c, l3.i, l3.price, "(3)"), _pt(c, h4.i, h4.price, "(4)")]
            if h5:
                pts += [_pt(c, l45[0], l45[1]), _pt(c, h5[0], h5[1], "(5)")]
            su = self._setup(c, f"KB-1:{_ts(c, l1)}:{_ts(c, h2)}", steps, 5, l1.i, c.i, lv, meta, pts)
            if su:
                out.append(su)
        return out

    def check(self, c: Ctx, st: Setup, i: int):
        P, s, m = self.P, c.s, st.meta
        atr = s.atr_ref(i)
        if (m["h4_conf"] or s.c[i] > m["h0"]) and s.c[i] > m["h4"] + P["invalid_above_atr"] * atr:
            return "invalid", {"reason": "giá đóng cửa vượt đỉnh (4)"}
        if st.state != "armed":
            return None
        h5 = max(m["h5"], s.h[i])
        if i - m["h5_i"] > P["trigger_window"]:
            return "invalid", {"reason": "quá hạn sau đỉnh (5)"}
        ok, info = bear_engulf(s, i, P)
        if ok and h5 <= m["h4"] - P["min_drop_atr"] * atr and min(m["h4"], h5) - m["l45"] >= P["pullback_min_atr"] * atr:
            q = min(1.0, info["body_atr"] / (2 * P["trigger_body_atr"]) + 0.5)
            return "triggered", self._final(st, i, c, q, f"nhấn chìm giảm thân {info['body_atr']} ATR dưới đỉnh (5) {h5:.2f}",
                                              max(m["h4"], h5), {"prev_low": m["l3"], "high_5": h5})
        if m["l45"] is not None and s.c[i] < m["l45"] - P["break_no_trigger_atr"] * atr:
            return "invalid", {"reason": "thủng đáy giữa (5) không có nến nhấn chìm"}
        return None


# ======================================================================================= KB-3 (vai-đầu-vai)
class KB3(Pattern):
    id = "KB-3"
    n_steps = 5

    def scan(self, c: Ctx) -> list[Setup]:
        P, pv, s = self.P, c.pv, c.s
        n = len(pv)
        if n < 7 or pv[-1].is_high or not pv[-2].is_high:
            return []
        ls, n1, hd, n2, rs = pv[-6], pv[-5], pv[-4], pv[-3], pv[-2]
        if not (ls.is_high and not n1.is_high and hd.is_high and not n2.is_high):
            return []
        if c.i - rs.i > P["max_after_rs_bars"] or hd.price <= max(ls.price, rs.price):
            return []
        atr = s.atr[c.i]
        fine = c.fine if c.fine is not None else pv
        lead = lx = None
        rng_hi = rng_lo = rh = mean_body = 0.0
        nb = 0
        cand = [k for k, p in enumerate(fine) if not p.is_high and p.i < ls.i]
        for k in reversed(cand[-int(P["max_pivots_back"]):]):      # đáy kết thúc sóng dẫn: mới -> cũ; mỗi đáy thử các sóng dẫn dài -> ngắn
            for ld in all_leads(c, fine, k, P):
                x = fine[k]
                a = x.i + 1
                hi_, lo_ = s.hi(a, c.i), s.lo(a, c.i)
                nb_ = c.i - x.i
                mb = sum(s.body(j) / s.atr_ref(j) for j in range(a, c.i + 1)) / max(1, nb_)
                if (nb_ >= P["range_min_bars"] and P["range_min_atr"] <= (hi_ - lo_) / atr
                        and (hi_ - lo_) <= P["range_max_lead_ratio"] * ld["height"] and hi_ < ld["h0"].price
                        and lo_ >= x.price - P["range_below_lead_ratio"] * ld["height"] and mb <= P["range_max_mean_body_atr"]):
                    lead, lx, rng_hi, rng_lo, rh, nb, mean_body = ld, x, hi_, lo_, hi_ - lo_, nb_, mb
                    break
            if lead:
                break
        if not lead:
            return []
        rng_ok = True
        neck = (n1.price + n2.price) / 2
        hh = hd.price - neck
        hs_ok = (hh > 0 and hd.price - max(ls.price, rs.price) >= P["head_min_ratio"] * hh
                 and abs(ls.price - rs.price) <= P["shoulder_tol"] * hh and abs(n1.price - n2.price) <= P["neck_tol"] * hh
                 and neck <= rng_lo + P["neck_in_lower"] * rh)
        last_c = s.c[c.i]
        near = (neck - P["neck_break_atr"] * atr) <= last_c <= (neck + P["neck_near_atr"] * atr)
        steps = [
            self.st(1, True, f"sóng dẫn {lead['hn']:.1f} ATR, {lead['longred']} nến đỏ dài, xanh {lead['green']:.0%}"),
            self.st(2, rng_ok, f"đi ngang {nb} nến, biên {rh / atr:.1f} ATR", closeness(mean_body, 0.5, 1.0)),
            self.st(3, hs_ok, f"vai-đầu-vai: vai {ls.price:.2f}/{rs.price:.2f}, đầu {hd.price:.2f}, cổ {neck:.2f}"),
            self.st(4, near, f"giá {last_c:.2f} về gần đường cổ {neck:.2f}"),
        ]
        meta = {"neck": neck, "head": hd.price, "rs": rs.price, "rs_i": rs.i, "ls": ls.price, "range_lo": rng_lo}
        lv = {"neckline": neck, "head": hd.price, "left_shoulder": ls.price, "right_shoulder": rs.price,
              "range_high": rng_hi, "range_low": rng_lo, "measured_move": neck - hh}
        pts = [_pt(c, ls.i, ls.price, "LS"), _pt(c, n1.i, n1.price), _pt(c, hd.i, hd.price, "H"),
               _pt(c, n2.i, n2.price), _pt(c, rs.i, rs.price, "RS")]
        su = self._setup(c, f"KB-3:{_ts(c, hd)}", steps, 4, hd.i, c.i, lv, meta, pts)
        return [su] if su else []

    def check(self, c: Ctx, st: Setup, i: int):
        P, s, m = self.P, c.s, st.meta
        atr = s.atr_ref(i)
        if s.h[i] > m["head"] or s.c[i] > m["rs"] + P["invalid_above_atr"] * atr:
            return "invalid", {"reason": "giá vượt vai phải/đầu"}
        ok, info = small_cluster(s, i, P)
        if s.c[i] < m["neck"] - P["neck_break_atr"] * atr and st.state == "armed" and not ok:
            return "invalid", {"reason": "thủng đường cổ trước khi có cụm nén"}
        if i - m["rs_i"] > P["max_after_rs_bars"]:
            return "invalid", {"reason": "quá hạn sau vai phải"}
        if st.state != "armed":
            return None
        if ok and info["lo"] >= m["neck"] - P["neck_break_atr"] * atr and info["hi"] <= m["neck"] + P["neck_near_atr"] * atr:
            q = 1.0 - min(0.5, info["range_atr"] / (2 * P["cluster_range_atr"]))
            return "triggered", self._final(
                st, i, c, q, f"cụm {int(P['cluster_bars'])} nến thân nhỏ (<= {info['max_body_atr']} ATR) sát đường cổ {m['neck']:.2f}",
                m["head"], {"neckline": m["neck"]})
        return None


# ======================================================================================= KB-4 (tiếp diễn sau phá đáy)
class KB4(Pattern):
    id = "KB-4"

    def scan(self, c: Ctx) -> list[Setup]:
        P, pv, s, out = self.P, c.pv, c.s, []
        n = len(pv)
        for k in range(max(0, n - int(P["max_pivots_back"])), n):
            if pv[k].is_high or pv[k].conf_i < 0:      # đáy neo phải đã XÁC NHẬN (đáy tạm thời đổi theo từng nến -> sinh khoá rác)
                continue
            lead = best_lead(c, k, P)
            if not lead:
                continue
            h0, l1 = lead["h0"], pv[k]
            # (1) đi ngang trước đó: hộp box_bars nến kết thúc tại h0
            a = max(0, h0.i - int(P["box_bars"]))
            if h0.i - a < P["box_min_bars"]:
                continue
            box_hi, box_lo = s.hi(a, h0.i), s.lo(a, h0.i)
            atr0 = s.atr[h0.i]
            box_h = (box_hi - box_lo) / atr0
            net = abs(s.c[h0.i] - s.c[a]) / max(box_hi - box_lo, 1e-12)
            box_ok = box_h <= P["box_max_atr"] and net <= P["box_max_net_ratio"]
            # (2) nến thân rất dài phá cạnh dưới
            bd = next((j for j in range(h0.i + 1, min(l1.i, h0.i + int(P["breakdown_within"])) + 1) if s.c[j] < box_lo), None)
            bd_ok = bd is not None and s.is_red(bd) and s.body(bd) / s.atr_ref(bd) >= P["breakdown_body_atr"]
            # (3) chuỗi nến đỏ liên tiếp từ nến phá đáy
            run = 0
            if bd is not None:
                j = bd
                while j <= l1.i and s.is_red(j):
                    run += 1
                    j += 1
            red_ok = run >= P["follow_red_min"]
            # (4)(5) đi ngang mới với 3 đỉnh giảm dần
            rest = pv[k + 1:]
            highs = [p for p in rest if p.is_high]
            lows = [p for p in rest if not p.is_high]
            atr = s.atr[c.i]
            nh = int(P["n_highs"])
            top = highs[-nh:] if len(highs) >= nh else []
            side_ok = bool(top) and all((x.price - y.price) >= P["min_drop_atr"] * atr for x, y in zip(top, top[1:])) \
                and top[0].price <= l1.price + P["retr_max"] * lead["height"] and top[0].price < h0.price \
                and all(p.price >= l1.price - P["pivot_tol_atr"] * atr for p in lows)
            steps = [
                self.st(1, box_ok, f"đi ngang trước: biên {box_h:.1f} ATR, lệch ròng {net:.0%}"),
                self.st(2, bd_ok, ("nến phá đáy thân %.1f ATR" % (s.body(bd) / s.atr_ref(bd))) if bd is not None else "chưa có nến phá đáy hộp"),
                self.st(3, red_ok, f"{run} nến đỏ liên tiếp; sóng dẫn {lead['hn']:.1f} ATR"),
                self.st(4, bool(highs) and highs[0].price < h0.price, f"{len(highs)} đỉnh trong vùng đi ngang mới"),
                self.st(5, side_ok, f"{nh} đỉnh giảm dần" if side_ok else f"mới {len(highs)} đỉnh"),
            ]
            if not (steps[0]["ok"] and steps[1]["ok"]):
                continue
            meta = {"h_top": top[0].price if top else None, "h_last": top[-1].price if top else None,
                    "h_last_i": top[-1].i if top else None, "l1": l1.price, "box_lo": box_lo, "h0": h0.price}
            lv = {"box_low": box_lo, "wave_high": h0.price, "wave_low": l1.price}
            if top:
                lv["high_1"], lv["high_last"] = top[0].price, top[-1].price
            state = "armed" if all(x["ok"] for x in steps) else "forming"
            steps.append(self.st(self.n_steps, False, "chờ cụm nến nén"))
            pts = [_pt(c, h0.i, h0.price), _pt(c, l1.i, l1.price, "(1)")] + [_pt(c, p.i, p.price, f"H{n + 1}") for n, p in enumerate(top)]
            out.append(Setup(self.id, f"KB-4:{_ts(c, l1)}", state, steps, score_of(steps, self.n_steps), lv, meta, l1.i, c.i, pts))
        return out

    def check(self, c: Ctx, st: Setup, i: int):
        P, s, m = self.P, c.s, st.meta
        atr = s.atr_ref(i)
        if m["h_top"] is not None and s.c[i] > m["h_top"] + P["invalid_above_atr"] * atr:
            return "invalid", {"reason": "giá đóng cửa vượt đỉnh đầu tiên của vùng đi ngang mới"}
        if s.c[i] < m["l1"] - P["break_no_trigger_atr"] * atr:
            return "invalid", {"reason": "thủng đáy sóng dẫn trước khi có cụm nén"}
        if st.state != "armed":
            return None
        if i - m["h_last_i"] > P["trigger_window"]:
            return "invalid", {"reason": "quá hạn sau đỉnh thứ 3"}
        ok, info = small_cluster(s, i, P)
        if ok and info["hi"] <= m["h_last"] + P["cluster_above_atr"] * atr:
            q = 1.0 - min(0.5, info["range_atr"] / (2 * P["cluster_range_atr"]))
            return "triggered", self._final(
                st, i, c, q, f"cụm {int(P['cluster_bars'])} nến nén dưới đỉnh thứ 3 {m['h_last']:.2f}", m["h_top"], {"prev_low": m["l1"]})
        return None


PATTERNS = {"KB-1": KB1, "KB-2": KB2, "KB-3": KB3, "KB-4": KB4}
