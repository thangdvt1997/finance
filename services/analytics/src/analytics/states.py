"""Trạng thái xu hướng/động lượng/biến động theo QUY TẮC MINH BẠCH + điểm tổng hợp.

Mỗi trạng thái có `rule` (điều kiện nguyên văn) để người dùng kiểm chứng. Đây là mô tả trạng thái chỉ báo kỹ thuật,
KHÔNG phải khuyến nghị đầu tư và không có khái niệm mua/bán.

- heat (0..100, không có hướng): mức độ "đáng chú ý" = 0.35*ADX(0..50 -> 0..100) + 0.25*|RSI-50|*2 + 0.25*phân vị ATR% + 0.15*|%B-0.5|*2.
- bias (-100..100): trung bình 5 phiếu chỉ báo (giá>EMA200, EMA20>EMA50, MACD hist>0, RSI>50, +DI>-DI) — độ nghiêng của chỉ báo.
"""
from __future__ import annotations

import numpy as np

from .indicators import last, percentile_rank

DISCLAIMER = "Chỉ báo kỹ thuật, không phải khuyến nghị đầu tư."


def _s(code: str, label: str, tone: str, rule: str, group: str) -> dict:
    return {"code": code, "label": label, "tone": tone, "rule": rule, "group": group}


def evaluate(ind: dict[str, np.ndarray]) -> dict:
    """Trả về {states[], trend, momentum, volatility, heat, bias, atr_percentile, squeeze, values{}}."""
    c = last(ind["close"])
    v = {k: last(a) for k, a in ind.items() if k not in {"open", "high", "low"}}
    atr_pctl = percentile_rank(ind["atr_pct"], v["atr_pct"])
    bbw_pctl = percentile_rank(ind["bb_width"], v["bb_width"], 120)
    st: list[dict] = []

    # ---- Xu hướng
    trend = "side"
    if v["ema200"] is not None and c is not None:
        if c > v["ema200"]:
            st.append(_s("above_ema200", "Giá trên EMA200", "up", "close > EMA200", "trend"))
        else:
            st.append(_s("below_ema200", "Giá dưới EMA200", "down", "close < EMA200", "trend"))
    e20, e50, e200 = v["ema20"], v["ema50"], v["ema200"]
    if None not in (e20, e50, e200):
        if e20 > e50 > e200:
            st.append(_s("ema_stack_up", "EMA xếp tăng (20>50>200)", "up", "EMA20 > EMA50 > EMA200", "trend"))
        elif e20 < e50 < e200:
            st.append(_s("ema_stack_down", "EMA xếp giảm (20<50<200)", "down", "EMA20 < EMA50 < EMA200", "trend"))
        else:
            st.append(_s("ema_mixed", "EMA đan xen", "neutral", "thứ tự EMA20/50/200 không đơn điệu", "trend"))
    adx = v["adx"]
    if adx is not None:
        if adx >= 25:
            st.append(_s("trend_strong", "Xu hướng rõ (ADX≥25)", "accent", "ADX(14) ≥ 25", "trend"))
        elif adx < 20:
            st.append(_s("range_bound", "Đi ngang (ADX<20)", "neutral", "ADX(14) < 20", "trend"))
    if None not in (c, e50, v["plus_di"], v["minus_di"], adx):
        if adx >= 20 and v["plus_di"] > v["minus_di"] and c > e50:
            trend = "up"
        elif adx >= 20 and v["minus_di"] > v["plus_di"] and c < e50:
            trend = "down"

    # ---- Động lượng
    rsi = v["rsi"]
    momentum = "neutral"
    if rsi is not None:
        if rsi >= 70:
            st.append(_s("rsi_overbought", "Quá mua (RSI≥70)", "warn", "RSI(14) ≥ 70", "momentum"))
            momentum = "overbought"
        elif rsi <= 30:
            st.append(_s("rsi_oversold", "Quá bán (RSI≤30)", "warn", "RSI(14) ≤ 30", "momentum"))
            momentum = "oversold"
        elif rsi > 50:
            momentum = "bullish"
        elif rsi < 50:
            momentum = "bearish"
    if v["macd_hist"] is not None:
        if v["macd_hist"] > 0:
            st.append(_s("macd_pos", "MACD histogram dương", "up", "MACD − Signal > 0", "momentum"))
        else:
            st.append(_s("macd_neg", "MACD histogram âm", "down", "MACD − Signal ≤ 0", "momentum"))
    k = v["stoch_k"]
    if k is not None:
        if k >= 80:
            st.append(_s("stoch_high", "Stochastic vùng cao (≥80)", "warn", "%K(14,3,3) ≥ 80", "momentum"))
        elif k <= 20:
            st.append(_s("stoch_low", "Stochastic vùng thấp (≤20)", "warn", "%K(14,3,3) ≤ 20", "momentum"))

    # ---- Biến động
    volatility = "normal"
    squeeze = bool(bbw_pctl is not None and bbw_pctl <= 20)
    if squeeze:
        st.append(_s("squeeze", "Squeeze (dải Bollinger co hẹp)", "accent",
                     "độ rộng Bollinger(20,2) ở phân vị ≤ 20 của 120 nến gần nhất", "volatility"))
        volatility = "squeeze"
    if atr_pctl is not None:
        if atr_pctl >= 80:
            st.append(_s("vol_high", "Biến động cao (ATR phân vị ≥80)", "warn", "ATR% ≥ phân vị 80 của lịch sử", "volatility"))
            volatility = "high"
        elif atr_pctl <= 20 and not squeeze:
            st.append(_s("vol_low", "Biến động thấp (ATR phân vị ≤20)", "neutral", "ATR% ≤ phân vị 20 của lịch sử", "volatility"))
            volatility = "low"
    if v["bb_upper"] is not None and c is not None:
        if c > v["bb_upper"]:
            st.append(_s("bb_above", "Giá ngoài dải Bollinger trên", "warn", "close > BB trên", "volatility"))
        elif c < v["bb_lower"]:
            st.append(_s("bb_below", "Giá ngoài dải Bollinger dưới", "warn", "close < BB dưới", "volatility"))

    # ---- Điểm tổng hợp
    votes = []
    if None not in (c, e200):
        votes.append(1 if c > e200 else -1)
    if None not in (e20, e50):
        votes.append(1 if e20 > e50 else -1)
    if v["macd_hist"] is not None:
        votes.append(1 if v["macd_hist"] > 0 else -1)
    if rsi is not None:
        votes.append(1 if rsi > 50 else -1 if rsi < 50 else 0)
    if None not in (v["plus_di"], v["minus_di"]):
        votes.append(1 if v["plus_di"] > v["minus_di"] else -1)
    bias = round(sum(votes) / len(votes) * 100) if votes else 0

    comp = []  # (trọng số, 0..100)
    if adx is not None:
        comp.append((0.35, min(adx, 50.0) / 50.0 * 100.0))
    if rsi is not None:
        comp.append((0.25, min(abs(rsi - 50.0) * 2.0, 100.0)))
    if atr_pctl is not None:
        comp.append((0.25, atr_pctl))
    if v["bb_pctb"] is not None:
        comp.append((0.15, min(abs(v["bb_pctb"] - 0.5) * 2.0, 1.0) * 100.0))
    wsum = sum(w for w, _ in comp)
    heat = round(sum(w * x for w, x in comp) / wsum) if wsum else 0

    return {"states": st, "trend": trend, "momentum": momentum, "volatility": volatility, "squeeze": squeeze,
            "heat": int(heat), "bias": int(bias), "atr_percentile": None if atr_pctl is None else round(atr_pctl, 1),
            "values": v}
