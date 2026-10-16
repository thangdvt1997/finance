"""Kiểm chứng engine: không look-ahead, khớp giải tích, tín hiệu ngẫu nhiên ~ 0. Chạy: python tests_sanity.py"""
import numpy as np, pandas as pd, engine as E, strategies as S
P = E.load_prices(E.FX + ["XAUUSD"]); rates, _ = E.load_rates(P.index)
fns = {"tsmom": S.tsmom, "ma": S.ma_cross, "donch": S.donchian, "rsi2": S.rsi2_mr, "boll": S.bollinger_mr, "carry": lambda p: S.carry(p, rates.loc[p.index])}
cut = P.index[-800]
for k, f in fns.items():
    cut2 = P.index[-806]; a = f(P).loc[:cut2]; b = f(P.loc[:cut]).loc[:cut2]
    assert a.fillna(-9).equals(b.fillna(-9)), f"look-ahead trong {k}"
print("OK: tín hiệu nhân quả (cắt dữ liệu tương lai không đổi tín hiệu quá khứ)")
# engine khớp giải tích: 1 instrument, +1, không vol-target/chi phí/carry
p1 = P[["EURUSD"]]; sig = pd.DataFrame(1.0, index=p1.index, columns=p1.columns)
out = E.run(p1, sig, rates, cost_mult=0, markup=0, vol_target=False)
vol = E.ewm_vol(p1.pct_change()).clip(lower=.02)
expect = (0.10/vol).clip(upper=4).shift(1) * p1.pct_change().shift(0)  # u = target/vol, q=u.shift(1)
spot = out["spot"]; ref = ((0.10/vol).clip(upper=4).shift(1)["EURUSD"] * p1.pct_change()["EURUSD"]).reindex(spot.index)
assert np.allclose(spot.values, ref.fillna(0).values, atol=1e-12), "engine không khớp giải tích"
print("OK: engine khớp giải tích (spot = vị thế trễ 1 ngày × lợi suất)")
# vị thế đổi dấu mỗi ngày -> chi phí = 2*|q|*half_cost
alt = pd.DataFrame(np.where(np.arange(len(p1)) % 2, 1.0, -1.0), index=p1.index, columns=p1.columns)
o2 = E.run(p1, alt, rates, vol_target=False, markup=0); assert o2["cost"].sum() > 0 and o2["net"].sum() < out["net"].sum()
print("OK: chi phí giao dịch tác động theo chiều đúng")
# ngẫu nhiên ~ 0
sh = []
for sd in range(60):
    m = S.month_end_mask(P.index); sg = S.random_signal(P, 0.5, m, sd)
    o = E.run(P, sg, rates, cost_mult=0, markup=0); sh.append(E.metrics(o["spot"])["Sharpe"])
print(f"OK: 60 chuỗi tín hiệu ngẫu nhiên (không phí): Sharpe trung bình {np.mean(sh):.3f}, độ lệch chuẩn {np.std(sh):.3f} (kỳ vọng ~0)")
assert abs(np.mean(sh)) < 0.15
