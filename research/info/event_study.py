"""Bien do quanh tin (NFP, FOMC) tu nen M1 HistData (bid; nhan thoi gian thuc te la gio ET co DST, da kiem bang dinh NFP 08:30 -> UTC=+4h mua he). Dukascopy khong truy cap duoc tu mang nay lan VPS.
Ngay kiem soat = cung thu, cung gio, +-1..3 tuan, khong trung ngay su kien. Khong co spread (nen M1 bid) -> xem tai lieu.
Tai lap: python fetch_histdata.py && python event_study.py"""
import zipfile, pathlib, glob
import numpy as np, pandas as pd
D = pathlib.Path(__file__).parent / "data" / "hd"; O = pathlib.Path(__file__).parent / "out"; O.mkdir(exist_ok=True)
PIP = {"EURUSD": 1e-4, "GBPUSD": 1e-4, "USDJPY": 1e-2, "XAUUSD": 0.1}
# NFP 08:30 ET=12:30 UTC; FOMC 14:00 ET=18:00 UTC (gio he). Ngay NFP T4-T6 chua doi chieu chinh thuc nhung se kiem bang chu ky bien dong.
EVENTS = [("NFP", "2026-04-03", 12, 30), ("NFP", "2026-05-08", 12, 30), ("NFP", "2026-06-05", 12, 30), ("NFP", "2026-07-02", 12, 30),
          ("NFP", "2026-08-07", 12, 30), ("NFP", "2026-09-04", 12, 30),
          ("FOMC", "2026-04-29", 18, 0), ("FOMC", "2026-06-17", 18, 0), ("FOMC", "2026-07-29", 18, 0), ("FOMC", "2026-09-16", 18, 0)]
CW = (-3, -2, -1, 1, 2, 3)

def load(sym):
    fr = []
    for f in sorted(glob.glob(str(D / f"{sym.lower()}_*.zip"))):
        z = zipfile.ZipFile(f); n = [x for x in z.namelist() if x.endswith(".csv")][0]
        d = pd.read_csv(z.open(n), sep=";", header=None, names=["t", "o", "h", "l", "c", "v"])
        fr.append(d)
    d = pd.concat(fr); d["t"] = pd.to_datetime(d.t, format="%Y%m%d %H%M%S") + pd.Timedelta(hours=4)  # thuc nghiem: nhan thoi gian = gio ET co DST (dinh NFP o 08:30) -> UTC = +4h (T4-T9)
    return d.set_index("t").sort_index()

def main():
    ev_days = {pd.Timestamp(d) for _, d, _, _ in EVENTS}; rows = []
    for sym, pip in PIP.items():
        m = load(sym)
        for kind, d, hh, mm in EVENTS:
            d0 = pd.Timestamp(d)
            for role, day in [("event", d0)] + [("control", d0 + pd.Timedelta(weeks=w)) for w in CW if (d0 + pd.Timedelta(weeks=w)) not in ev_days]:
                T = day + pd.Timedelta(hours=hh, minutes=mm)
                def w(a, b): return m[(m.index >= T + pd.Timedelta(minutes=a)) & (m.index < T + pd.Timedelta(minutes=b))]
                pre, p1, p5, p30, p60 = w(-30, 0), w(0, 1), w(0, 5), w(0, 30), w(0, 60)
                if len(pre) < 20 or len(p30) < 20: continue
                rg = lambda x: (x.h.max() - x.l.min()) / pip
                ref = pre.c.iloc[-1]
                pre_bar = ((pre.h - pre.l) / pip).median(); pb = ((p60.h - p60.l) / pip)
                calm = np.nan
                for k, v in enumerate(pb.values):  # phut dau tien ma bien do 1 phut <= 2x trung vi pre va giu 3 phut lien tiep
                    if k >= 1 and (pb.values[k:k + 3] <= 2 * max(pre_bar, 1e-9)).all(): calm = k; break
                day_rg = m[(m.index >= day) & (m.index < day + pd.Timedelta(days=1))]
                exc = (p30.h.max() - ref) / pip, (ref - p30.l.min()) / pip
                mv30 = (p30.c.iloc[-1] - ref) / pip; mv5 = (p5.c.iloc[-1] - ref) / pip
                big = max(exc, key=abs)
                rows.append(dict(kind=kind, date=d0.date(), role=role, sym=sym, range_pre30=rg(pre), range_0_1=rg(p1) if len(p1) else np.nan,
                    range_0_5=rg(p5), range_0_30=rg(p30), range_0_60=rg(p60), pre_bar_med=pre_bar, calm_min=calm,
                    move_5=mv5, move_30=mv30, maxexc_30=max(exc), retrace30=(max(exc) - abs(mv30)) / max(exc) if max(exc) > 0 else np.nan,
                    day_range=rg(day_rg) if len(day_rg) > 500 else np.nan))
    R = pd.DataFrame(rows); R.to_csv(O / "event_windows.csv", index=False)
    pd.set_option("display.width", 220)
    print("rows", len(R), R.groupby(["kind", "role"]).size().to_dict())
    print(R.groupby(["kind", "sym", "role"])[["range_pre30", "range_0_5", "range_0_30", "range_0_60", "day_range", "calm_min"]].median().round(1).to_string())
    rng = np.random.default_rng(1); res = []
    for (kind, sym), s in R.groupby(["kind", "sym"]):
        for col in ("range_pre30", "range_0_1", "range_0_5", "range_0_30", "range_0_60", "day_range"):
            e = s[s.role == "event"][col].dropna().to_numpy(); c = s[s.role == "control"][col].dropna().to_numpy()
            if len(e) < 3 or len(c) < 5: continue
            rat = [np.median(rng.choice(e, len(e))) / np.median(rng.choice(c, len(c))) for _ in range(4000)]
            res.append(dict(kind=kind, sym=sym, metric=col, n_e=len(e), n_c=len(c), med_e=np.median(e), med_c=np.median(c), ratio=np.median(e) / np.median(c), lo=np.percentile(rat, 2.5), hi=np.percentile(rat, 97.5)))
    X = pd.DataFrame(res); X.to_csv(O / "event_ratios.csv", index=False); print(X.round(2).to_string())
    E = R[R.role == "event"].copy(); E["fade"] = np.sign(E.move_5) != np.sign(E.move_30)
    print("\nfade dau move5 != move30:"); print(E.groupby("kind").fade.agg(["mean", "count"]).round(2).to_string())
    print("\nretrace30 trung vi (spike hoi lai bao nhieu trong 30p) event vs control:"); print(R.groupby(["kind", "role"]).retrace30.median().round(2).to_string())
    print("\ncalm_min (phut den khi bien do 1 phut <=2x binh thuong) event:", E.groupby("kind").calm_min.median().to_dict())
    pooled = X.groupby(["kind", "metric"]).apply(lambda d: pd.Series({"gmean_ratio": float(np.exp(np.log(d.ratio).mean())), "min": d.ratio.min(), "max": d.ratio.max()})).round(2)
    print("\nPOOLED 4 ma:"); print(pooled.to_string())
    # kiem tra ngay NFP T4-T6: bien do 0-5 phut / control, theo ngay (ma EURUSD)
    ee = R[(R.sym == "EURUSD")].copy(); base = ee[ee.role == "control"].groupby("kind").range_0_5.median()
    ee = ee[ee.role == "event"]; ee["x_ctrl"] = ee.range_0_5 / ee.kind.map(base); print("\nEURUSD range_0_5 / median control theo ngay su kien:"); print(ee[["kind", "date", "range_0_5", "x_ctrl"]].round(2).to_string())

main()
