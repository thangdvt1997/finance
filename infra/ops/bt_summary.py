#!/usr/bin/env python3
"""Sinh docs/research/pattern_sell/summary.json (bảng tóm tắt tab "Backtest") từ sổ lệnh đã đóng băng.
Chỉ đọc ledger_{dev,val,test}.csv.gz; p vs ngẫu nhiên + baseline lấy từ báo cáo (docs/research/PATTERN_SELL_BACKTEST.md §3.1, §5).
Bootstrap CI95 seed cố định. Không đọc/chạy lại tập test ngoài sổ lệnh đã công bố."""
import gzip, json, sys
from pathlib import Path
import numpy as np, pandas as pd

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "data/research/patterns/backtest/final/ledger")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/research/pattern_sell/summary.json")
rng = np.random.default_rng(20261014)


def stat(r: pd.Series, gross: pd.Series, baseline=None, p=None, label="", note=""):
    x = r.to_numpy(float)
    n = len(x)
    bs = x[rng.integers(0, n, (4000, n))].mean(axis=1)
    win, loss = x[x > 0].sum(), -x[x < 0].sum()
    return {"label": label, "n": n, "win": round(float((x > 0).mean()), 4), "exp_r": round(float(x.mean()), 4),
            "ci_lo": round(float(np.percentile(bs, 2.5)), 4), "ci_hi": round(float(np.percentile(bs, 97.5)), 4),
            "pf": round(float(win / loss), 3) if loss else None, "exp_gross": round(float(gross.mean()), 4),
            "baseline": baseline, "p_random": p, "note": note}


d = {s: pd.read_csv(SRC / f"ledger_{s}.csv.gz") for s in ("dev", "val", "test")}
dv = pd.concat([d["dev"], d["val"]])
rows = [
    stat(d["dev"].R_net, d["dev"].R_gross, label="Dev (walk-forward ngoài mẫu 2008 – 07/2025)"),
    stat(d["val"].R_net, d["val"].R_gross, label="Val (08/2025 – 03/2026)"),
    stat(dv.R_net, dv.R_gross, -0.126, 0.0199, "Dev + Val gộp (8.290 lệnh)", "p một phía: P(ngẫu nhiên ≥ thật)"),
    stat(d["test"].R_net, d["test"].R_gross, -0.157, 0.9701, "Test khoá (03/2026 – 10/2026, chạy 1 lần)", "Kém cả vào lệnh ngẫu nhiên"),
]
by_kb = {}
for name, df in (("dev_val", dv), ("test", d["test"])):
    by_kb[name] = [stat(g.R_net, g.R_gross, label=k) for k, g in df.groupby("kb")]
OUT.write_text(json.dumps({
    "verdict": "Không có edge sau chi phí",
    "detail": "Kỳ vọng âm sau chi phí ở cả dev, val và test khoá; không tốt hơn vào lệnh ngẫu nhiên trên tập test. Không có bằng chứng edge.",
    "rows": rows, "by_kb": by_kb, "unit": "R/lệnh, sau spread + trượt + phí",
}, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(rows, ensure_ascii=False, indent=1))
