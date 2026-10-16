"""Chay moi mo phong (luoi tham so, benchmark, do nhay, placebo) -> $ROUT/vn_*.parquet|csv|json. Tinh thong ke/hinh o analyze_vn.py.
Cau hinh CHINH (khai bao TRUOC khi chay): momentum 12-1, universe top-100 theo thanh khoan (xap xi VN100 theo thoi diem), top-15, rebalance thang, EW, KHONG loc.
Cau hinh PHONG THU (khai bao truoc): nhu tren + loc VN-Index > SMA200 danh gia moi cuoi thang (giu tien mat neu duoi).
Dung: python run_vn.py [stage ...]  stage in: grid bench sens placebo last (mac dinh: tat ca)."""
import itertools, json, sys, time
from multiprocessing import Pool
import numpy as np, pandas as pd
from vn_common import *
from vn_engine import *
from vn_strats import *

t_start = time.time()
df = load_raw(); P = Panel(df)
idx_raw = pd.read_parquet(DATA / "vn_index_raw.parquet")
vni, vstat = build_vni(P, idx_raw); REG = regime(vni)
ST = int(np.searchsorted(P.dates, START)) - 5
LOOKS = {3: 63, 6: 126, 9: 189, 12: 252}; SKIPS = {0: 0, 1: 21}
SIG = {(lb, sk): P.mom(LOOKS[lb], SKIPS[sk]) for lb in LOOKS for sk in SKIPS}
now = json.load(open(DATA / "vn_universe_now.json")) if (DATA / "vn_universe_now.json").exists() else {"vn100": [], "vn30": []}
alive = P.last_idx >= P.T - 5
RANKS = {"all": P.rank_tv,
         "survivors": universe_rank(P, alive),
         "vn100now": universe_rank(P, np.array([c in set(now["vn100"]) for c in P.codes]))}
PRIM = dict(lb=12, skip=1, uni=100, N=15, freq="M", weight="ew", filt="none")


def run_spec(sp):
    S = SIG[(sp["lb"], sp["skip"])]
    reg = None
    if sp["filt"] != "none":
        reg = REG if not sp.get("shift") else np.roll(REG, int(sp["shift"]))
    rng = np.random.default_rng(sp["seed"]) if sp.get("rand") else None
    dec = momentum(P, S, sp["N"], sp["uni"], sp["weight"], reg, rng=rng, rand=bool(sp.get("rand")), sign=sp.get("sign", 1.0),
                   rank=RANKS[sp.get("universe", "all")], pos_only=bool(sp.get("pos_only")))
    tr = triggers(P, sp["freq"], reg, "D" if sp["filt"] == "D" else "M")
    cfg = Cfg(start=ST, **sp.get("cfg", {}))
    res = simulate(P, dec, tr, cfg, want_log=bool(sp.get("log")))
    out = summarize(res, label=sp["key"])
    if sp.get("log"): out["log"] = [(str(a.date()), b, c, float(d), float(e)) for a, b, c, d, e in res["log"]]
    return sp["key"], res["ret"], out, res["expo"]


def key_of(sp):
    return f'M{sp["lb"]}-{sp["skip"]}|U{sp["uni"]}|N{sp["N"]}|{sp["freq"]}|{sp["weight"]}|{sp["filt"]}'


def run_many(specs, procs=6):
    for sp in specs: sp.setdefault("key", key_of(sp))
    with Pool(procs) as pool:
        out = pool.map(run_spec, specs, chunksize=3)
    R = pd.DataFrame({k: r for k, r, _, _ in out}); tab = pd.DataFrame([s for _, _, s, _ in out]).set_index("label")
    E = pd.DataFrame({k: e for k, _, _, e in out})
    return R, tab, E


def stage_grid():
    specs = []
    for lb, sk, uni, N, fq, w, fl in itertools.product([3, 6, 9, 12], [0, 1], [30, 100], [10, 15, 20, 30], ["M", "Q"], ["ew", "iv"], ["none", "M", "D"]):
        if N >= uni: continue                        # N=30 trong U30 = giu ca universe (khong phai chon loc)
        specs.append(dict(lb=lb, skip=sk, uni=uni, N=N, freq=fq, weight=w, filt=fl))
    print("grid specs", len(specs), flush=True)
    R, tab, E = run_many(specs)
    R.to_parquet(OUT / "vn_grid_returns.parquet"); tab.to_csv(OUT / "vn_grid.csv"); E.to_parquet(OUT / "vn_grid_expo.parquet")
    print("grid done", len(tab), round(time.time() - t_start), "s", flush=True)


def bench_decide():
    j_etf = P.cidx.get("E1VFVN30")
    first_etf = int(P.first_idx[j_etf]) + 25
    out = {}
    r_m = period_ends(P.dates, "M", START); r_q = period_ends(P.dates, "Q", START)
    cfg = Cfg(start=ST)
    out["EW30_Q"] = simulate(P, ew_universe(P, 30), r_q, cfg)
    out["EW100_Q"] = simulate(P, ew_universe(P, 100), r_q, cfg)
    out["EW100_M"] = simulate(P, ew_universe(P, 100), r_m, cfg)
    out["EW30_M"] = simulate(P, ew_universe(P, 30), r_m, cfg)
    etf_tr = np.array([first_etf])
    out["ETF_BH"] = simulate(P, lambda i: {j_etf: 1.0}, etf_tr, Cfg(start=first_etf - 5))
    for mode in ["M", "D"]:
        dec = lambda i: ({j_etf: 1.0} if REG[i] else {})
        tr = triggers(P, "M", REG, mode, start=P.dates[first_etf])
        out[f"ETF_MA200_{mode}"] = simulate(P, dec, tr, Cfg(start=first_etf - 5))
    res = {k: v for k, v in out.items()}
    # chi so (mua giu, khong chi phi) + tien mat
    res["VNINDEX_BH"] = index_result(vni, P.dates[ST + 5])
    cash_idx = pd.Series(np.cumprod(np.full(P.T - ST, 1 + RF / ANN)), index=P.dates[ST:])
    res["CASH"] = dict(nav=cash_idx, ret=cash_idx.pct_change().dropna(), expo=pd.Series(0.0, index=cash_idx.index), nheld=pd.Series(0.0, index=cash_idx.index),
                       turnover_yr=0.0, cost_yr=0.0)
    # VNINDEX + MA200 (khong chi phi) de doi chieu bo loc
    lv = vni.copy(); r = lv.pct_change().fillna(0.0)
    for mode, name in [("M", "VNI_MA200_M"), ("D", "VNI_MA200_D")]:
        pos = pd.Series(0.0, index=P.dates)
        if mode == "D": pos = pd.Series(REG.astype(float), index=P.dates)
        else:
            me = period_ends(P.dates, "M", START); cur = 0.0; arr = np.zeros(P.T); k = 0; mset = set(me)
            for i in range(P.T):
                if i in mset: cur = float(REG[i])
                arr[i] = cur
            pos = pd.Series(arr, index=P.dates)
        rr = (pos.shift(2).fillna(0.0) * r + (1 - pos.shift(2).fillna(0.0)) * RF / ANN).loc[P.dates[ST + 5]:]
        nav = (1 + rr).cumprod()
        res[name] = dict(nav=nav, ret=rr, expo=pos.loc[nav.index], nheld=pd.Series(1.0, index=nav.index), turnover_yr=np.nan, cost_yr=0.0)
    return res


def stage_bench():
    res = bench_decide()
    R = pd.DataFrame({k: v["ret"] for k, v in res.items()}); R.to_parquet(OUT / "vn_bench_returns.parquet")
    tab = pd.DataFrame([summarize(v, label=k) for k, v in res.items()]).set_index("label"); tab.to_csv(OUT / "vn_bench.csv")
    pd.DataFrame({k: v["expo"] for k, v in res.items()}).to_parquet(OUT / "vn_bench_expo.parquet")
    vni.to_frame("vni_chain").to_parquet(OUT / "vn_vni_chain.parquet")
    json.dump(vstat, open(OUT / "vn_vni_stats.json", "w"), indent=1)
    print(tab[["Sharpe", "CAGR", "Vol", "MaxDD", "start"]].round(3), flush=True)


def stage_sens():
    specs = []
    def add(tag, base, **kw):
        sp = dict(PRIM); sp.update(base); sp.update(kw); sp["key"] = tag; specs.append(sp)
    for flt in ["none", "M"]:
        b = dict(filt=flt); t = "P" if flt == "none" else "F"
        add(f"{t}|base", b)
        for cmult in [0.0, 0.5, 1.0, 2.0, 3.0]: add(f"{t}|cost x{cmult}", b, cfg=dict(cost_mult=cmult))
        for cap in [1e9, 5e9, 2e10, 5e10, 2e11, 1e12]: add(f"{t}|capital {cap:.0e}", b, cfg=dict(capital=cap))
        for pc in [0.02, 0.05, 0.10, 0.20]: add(f"{t}|part_cap {pc}", b, cfg=dict(part_cap=pc))
        add(f"{t}|fill close", b, cfg=dict(fill="close")); add(f"{t}|fill open", b, cfg=dict(fill="open"))
        add(f"{t}|buy delay 1 (no T+2 wait)", b, cfg=dict(buy_delay=1)); add(f"{t}|sell delay 2 buy 4", b, cfg=dict(sell_delay=2, buy_delay=4))
        add(f"{t}|slip x2 only", b, cfg=dict(slip_base_bps=10.0, impact_bps=20.0))
        add(f"{t}|delist haircut 50%", b, cfg=dict(delist_haircut=0.5))
        add(f"{t}|invest 100%", b, cfg=dict(invest=1.0)); add(f"{t}|invest 90%", b, cfg=dict(invest=0.90))
        add(f"{t}|survivors-only universe", b, universe="survivors")
        add(f"{t}|today VN100 universe", b, universe="vn100now")
        add(f"{t}|losers (sign -1)", b, sign=-1.0)
        add(f"{t}|pos-only", b, pos_only=True)
        add(f"{t}|weight iv", b, weight="iv"); add(f"{t}|U30", b, uni=30, N=10)
    add("F|daily filter", dict(filt="D"))
    R, tab, E = run_many(specs)
    R.to_parquet(OUT / "vn_sens_returns.parquet"); tab.to_csv(OUT / "vn_sens.csv"); E.to_parquet(OUT / "vn_sens_expo.parquet")
    print(tab[["Sharpe", "CAGR", "MaxDD", "TurnoverYr", "CostYr", "Expo"]].round(3).to_string(), flush=True)


def stage_placebo():
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 200
    specs = []
    for s in range(n):
        sp = dict(PRIM); sp.update(rand=True, seed=1000 + s, key=f"rand|none|{s}"); specs.append(sp)
        sp = dict(PRIM); sp.update(rand=True, seed=5000 + s, filt="M", key=f"rand|M|{s}"); specs.append(sp)
    rng = np.random.default_rng(11)
    for s in range(n):   # placebo thoi diem: dich vong tron che do thi truong >= 1 nam (giu ty le ON/OFF), chon top-15 that
        k = int(rng.integers(252, P.T - 252))
        sp = dict(PRIM); sp.update(filt="M", shift=k, key=f"shift|M|{s}|{k}"); specs.append(sp)
    R, tab, E = run_many(specs)
    R.to_parquet(OUT / "vn_placebo_returns.parquet"); tab.to_csv(OUT / "vn_placebo.csv")
    print("placebo done", len(tab), flush=True)


def stage_last():
    out = {}
    for name, flt in [("PRIMARY", "none"), ("DEFENDED", "M")]:
        sp = dict(PRIM); sp["filt"] = flt; sp["key"] = name; sp["log"] = True
        key, r, s, e = run_spec(sp)
        out[name] = dict(summary={k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in s.items() if k != "log"}, log_tail=s["log"][-60:])
    S = SIG[(12, 1)]; i = P.T - 1
    cand = np.flatnonzero((P.rank_tv[i] <= 100) & np.isfinite(S[i]))
    top = cand[np.argsort(-S[i, cand])[:15]]
    out["latest"] = dict(date=str(P.dates[i].date()), regime_on=bool(REG[i]), vni=float(vni.iloc[-1]), vni_ma200=float(vni.rolling(200).mean().iloc[-1]),
                         top15=[dict(code=P.codes[j], mom=float(S[i, j]), close=float(P.Cf[i, j]), rank_liq=int(P.rank_tv[i, j])) for j in top])
    json.dump(out, open(OUT / "vn_last.json", "w"), indent=1, default=str)
    print(json.dumps(out["latest"], indent=1), flush=True)


def etf_spec_run(args):
    """ETF E1VFVN30 giu khi tin hieu xu huong BAT: nguon = 'etf' (gia ETF) | 'vni' (VNI chain); ma = so phien SMA; mode M|D; shift (placebo)."""
    src, ma, mode, shift, cost = args
    j = P.cidx["E1VFVN30"]; first_etf = int(P.first_idx[j]) + 25
    lvl = pd.Series(P.ACf[:, j], index=P.dates) if src == "etf" else vni
    reg = regime(lvl, ma)
    if shift: reg = np.roll(reg, int(shift))
    tr = triggers(P, "M", reg, mode, start=P.dates[first_etf])
    res = simulate(P, lambda i: ({j: 1.0} if reg[i] else {}), tr, Cfg(start=first_etf - 5, cost_mult=cost))
    r = res["ret"]
    return args, r, summarize(res)


def stage_extra():
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 200
    specs = []
    # (1) cung universe, chi phi 0: EW100 + placebo ngau nhien (do suc manh THUAN cua tin hieu)
    for k, fq in [("EW100_M", "M"), ("EW100_Q", "Q"), ("EW30_Q", "Q")]:
        pass
    r_m = period_ends(P.dates, "M", START); r_q = period_ends(P.dates, "Q", START)
    ew0 = {"EW100_M|cost0": simulate(P, ew_universe(P, 100), r_m, Cfg(start=ST, cost_mult=0.0)),
           "EW100_Q|cost0": simulate(P, ew_universe(P, 100), r_q, Cfg(start=ST, cost_mult=0.0)),
           "EW30_Q|cost0": simulate(P, ew_universe(P, 30), r_q, Cfg(start=ST, cost_mult=0.0)),
           "EW100_Q|cost2": simulate(P, ew_universe(P, 100), r_q, Cfg(start=ST, cost_mult=2.0))}
    Rb = pd.DataFrame({k: v["ret"] for k, v in ew0.items()})
    sp = []
    for s in range(n):
        d = dict(PRIM); d.update(rand=True, seed=9000 + s, cfg=dict(cost_mult=0.0), key=f"rand0|none|{s}"); sp.append(d)
    Rr, tab, _ = run_many(sp)
    # (2) ETF + xu huong: luoi MA x che do x nguon
    etf_args = [(src, ma, mode, 0, 1.0) for src in ["etf", "vni"] for ma in [100, 150, 200, 250, 300] for mode in ["M", "D"]]
    rng = np.random.default_rng(23)
    etf_args += [("etf", 200, "M", int(rng.integers(252, P.T - 252)), 1.0) for _ in range(n)]
    with Pool(6) as pool: eo = pool.map(etf_spec_run, etf_args, chunksize=2)
    Re = pd.DataFrame({("|".join(map(str, a))): r for a, r, _ in eo}); te = pd.DataFrame([{**s, "label": "|".join(map(str, a))} for a, _, s in eo]).set_index("label")
    # (3) momentum chi phi 0 voi cac cau hinh chinh (de co Sharpe gop)
    Rb.to_parquet(OUT / "vn_extra_ew0.parquet"); Rr.to_parquet(OUT / "vn_extra_rand0.parquet"); Re.to_parquet(OUT / "vn_extra_etf.parquet"); te.to_csv(OUT / "vn_extra_etf.csv")
    print(te.loc[[i for i in te.index if i.split("|")[3] == "0"], ["Sharpe", "CAGR", "MaxDD", "Expo", "TurnoverYr"]].round(3).to_string(), flush=True)


if __name__ == "__main__":
    stages = [a for a in sys.argv[1:] if not a.startswith("--") and a in ("grid", "bench", "sens", "placebo", "last", "extra")] or ["bench", "grid", "sens", "placebo", "last"]
    print("panel", P.T, P.N, "vni stats", vstat, flush=True)
    for st in stages:
        t0 = time.time(); globals()["stage_" + st](); print(f"[{st}] {time.time()-t0:.0f}s", flush=True)
