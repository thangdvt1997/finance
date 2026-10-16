"""Registry chiến lược/kịch bản = file YAML (registry/*.yaml); thêm mới KHÔNG cần code. Số liệu backtest của KB-* được đọc THẬT
từ hiện vật backtest (summary.json) lúc chạy, không chép tay vào YAML. Tự nạp lại khi file đổi (so mtime)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from .scenario_store import Store, scenario_strategy

MODULES = {"pattern", "ml", "llm", "consensus", "rl", "risk"}
STATUSES = {"research", "paper", "paused"}
VERDICTS = {"no_edge", "unproven", "edge"}
BACKLOG_STATUS = {"idea", "planned", "running", "done", "dropped"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,47}$")
FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,95}$")
SPECIAL = {"backlog.yaml", "lab.yaml"}


def _vi(x: float, fmt: str) -> str:
    return format(x, fmt).replace(".", ",")


def _f(v):
    return None if v is None else float(v)


class Registry:
    def __init__(self, reg_dir: str, research_dir: str, state_dir: str | None = None):
        self.reg = Path(reg_dir)
        self.res = Path(research_dir)
        self.store = Store(state_dir) if state_dir else None
        self._sig: tuple | None = None
        self._data: dict = {}

    # ---- nạp YAML (cache theo mtime) ----
    def _signature(self) -> tuple:
        files = sorted(self.reg.glob("*.yaml")) if self.reg.is_dir() else []
        sj = self.res / "summary.json"
        sc = []
        if self.store:
            for sid in self.store.ids():
                for fn in ("scenario.yaml", "result.json", "test_opened.json"):
                    f = self.store.sdir / sid / fn
                    sc.append((sid + "/" + fn, f.stat().st_mtime_ns if f.exists() else 0))
        return tuple((f.name, f.stat().st_mtime_ns) for f in files) + ((("summary", sj.stat().st_mtime_ns),) if sj.is_file() else ()) + tuple(sc)

    def load(self) -> dict:
        sig = self._signature()
        if sig == self._sig:
            return self._data
        strategies, errors = {}, []
        backlog, lab = [], []
        for f in sorted(self.reg.glob("*.yaml")) if self.reg.is_dir() else []:
            try:
                doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except (yaml.YAMLError, OSError) as e:
                errors.append(f"{f.name}: {type(e).__name__}")
                continue
            if f.name == "backlog.yaml":
                backlog = [b for b in (doc.get("items") or []) if isinstance(b, dict) and b.get("id")]
            elif f.name == "lab.yaml":
                lab = [x for x in (doc.get("experiments") or []) if isinstance(x, dict)]
            elif isinstance(doc, dict) and ID_RE.match(str(doc.get("id", ""))) and doc.get("module") in MODULES:
                if doc.get("status") not in STATUSES or doc.get("verdict", "unproven") not in VERDICTS:
                    errors.append(f"{f.name}: status/verdict không hợp lệ")
                    continue
                strategies[str(doc["id"])] = doc
            else:
                errors.append(f"{f.name}: thiếu id/module hợp lệ")
        if self.store:
            for sid in self.store.ids():
                doc = scenario_strategy(self.store, sid)
                if doc and sid not in strategies:
                    strategies[sid] = doc
                else:
                    errors.append(f"kịch bản {sid}: không đọc được hoặc trùng id")
        summary = None
        sj = self.res / "summary.json"
        if sj.is_file():
            try:
                summary = json.loads(sj.read_text(encoding="utf-8"))
            except ValueError:
                errors.append("summary.json: không đọc được")
        self._data = {"strategies": strategies, "backlog": backlog, "lab": lab, "summary": summary, "errors": errors}
        self._sig = sig
        return self._data

    # ---- hiện vật ----
    def files(self, kind: str) -> list[str]:
        d = self.res / kind
        return sorted(f.name for f in d.glob("*.png") if FILE_RE.match(f.name)) if d.is_dir() else []

    def media_path(self, kind: str, name: str) -> Path | None:
        if kind not in ("charts", "examples") or not FILE_RE.match(name) or not name.endswith(".png"):
            return None
        p = self.res / kind / name
        return p if p.is_file() else None

    @staticmethod
    def media_url(kind: str, name: str) -> str:
        return f"/v1/ai-trading/media/{kind}/{name}"

    # ---- số liệu thật của KB từ summary.json ----
    def _row(self, rows: list[dict], label: str) -> dict | None:
        return next((r for r in rows if r.get("label") == label), None)

    def pattern_sell_numbers(self, kb: str) -> dict | None:
        s = self.load()["summary"]
        if not s:
            return None
        dv = self._row((s.get("by_kb") or {}).get("dev_val", []), kb)
        te = self._row((s.get("by_kb") or {}).get("test", []), kb)
        agg = {r["label"].split(" ")[0]: r for r in s.get("rows", [])}
        agg_test = next((r for r in s.get("rows", []) if r["label"].startswith("Test")), None)
        if not dv or not te:
            return None
        return {"dev_val": dv, "test": te, "aggregate_test": agg_test, "aggregate": agg}

    def metrics(self, st: dict) -> dict:
        src = st.get("source") or {}
        if src.get("type") == "pattern_sell":
            n = self.pattern_sell_numbers(str(src.get("kb")))
            if n:
                return {"expectancy_r": _f(n["dev_val"]["exp_r"]), "p_vs_random": _f(n["aggregate_test"]["p_random"]) if n["aggregate_test"] else None,
                        "trades": int(n["dev_val"]["n"]) + int(n["test"]["n"]), "expectancy_r_test": _f(n["test"]["exp_r"]),
                        "scope_note": "expectancy_r = walk-forward dev+val của KB; p_vs_random = p của TẬP TEST KHOÁ gộp 4 KB (không tính riêng từng KB)"}
        m = st.get("metrics") or {}
        if st.get("origin") == "user":
            return {"expectancy_r": _f(m.get("expectancy_r")), "p_vs_random": _f(m.get("p_vs_random")), "trades": m.get("trades"),
                    "scope_note": m.get("scope_note")}
        return {"expectancy_r": _f(m.get("expectancy_r")), "p_vs_random": _f(m.get("p_vs_random")), "trades": m.get("trades")}

    def card(self, st: dict) -> dict:
        c = {"id": str(st["id"]), "name": st.get("name", st["id"]), "module": st["module"], "status": st["status"],
             "summary": st.get("summary", ""), "metrics": self.metrics(st), "verdict": st.get("verdict", "unproven"),
             "warning": st.get("warning")}
        if st.get("origin") == "user":
            c["origin"] = "user"
            c["phase"] = st.get("phase")
        return c

    def detail(self, st: dict, audience: str) -> dict:
        out = self.card(st)
        src = st.get("source") or {}
        bt = None
        charts: list[str] = []
        examples: list[dict] = []
        if src.get("type") == "pattern_sell":
            kb = str(src.get("kb"))
            n = self.pattern_sell_numbers(kb)
            if n:
                dv, te, ag = n["dev_val"], n["test"], n["aggregate_test"] or {}
                s = self.load()["summary"]
                dev_row = self._row(s["rows"], "Dev (walk-forward ngoài mẫu 2008 – 07/2025)")
                val_row = next((r for r in s["rows"] if r["label"].startswith("Val")), None)

                def sp(r):
                    return None if not r else {"n": r["n"], "expectancy_r": _f(r["exp_r"]), "ci95": [_f(r["ci_lo"]), _f(r["ci_hi"])]}
                bt = {"expectancy_r": _f(dv["exp_r"]), "ci95": [_f(dv["ci_lo"]), _f(dv["ci_hi"])],
                      "p_vs_random": _f(ag.get("p_random")), "max_dd_r": _f(src.get("agg_max_dd_r_test")), "trades": int(dv["n"]) + int(te["n"]),
                      "splits": {"dev": sp(dv), "val": None, "test": sp(te)},
                      "scope_note": ("splits.dev = walk-forward dev+val của riêng KB này (tách dev/val chỉ có ở mức gộp 4 KB: "
                                     f"dev {sp(dev_row)['expectancy_r'] if dev_row else None} R, val {sp(val_row)['expectancy_r'] if val_row else None} R). "
                                     "p_vs_random và max_dd_r là của TẬP TEST KHOÁ gộp 4 KB."),
                      "aggregate_test": {"n": ag.get("n"), "expectancy_r": _f(ag.get("exp_r")), "p_vs_random": _f(ag.get("p_random")),
                                         "baseline_random_r": _f(ag.get("baseline"))}}
                if audience == "master":
                    charts = [self.media_url("charts", c) for c in self.files("charts") if not c.startswith("i_golden_") or c == f"i_golden_{kb.lower()}.png"]
                    for fn in self.files("examples"):
                        if fn.startswith(f"{kb}_"):
                            res = "win" if "_thang_" in fn else "loss" if "_thua_" in fn else "worst" if "_te-nhat_" in fn else "other"
                            examples.append({"id": fn[:-4], "result": res, "image_url": self.media_url("examples", fn)})
        elif st.get("origin") == "user":
            bt = self.scenario_backtest(st)
        else:
            b = st.get("backtest")
            if isinstance(b, dict):
                bt = b
        out["backtest"] = bt
        if st.get("origin") == "user":
            out["scenario"] = self.scenario_info(st, audience)
        out["forward_paper"] = st.get("forward_paper")
        out["honesty_note"] = st.get("honesty_note") or "Chưa có bằng chứng thống kê; mọi kết quả chỉ là nghiên cứu/mô phỏng (paper), không phải khuyến nghị."
        if audience == "master":
            out["charts"] = charts
            out["examples"] = examples
            out["doc"] = st.get("doc")
        return out

    @staticmethod
    def scenario_backtest(st: dict) -> dict | None:
        res = st.get("result") or {}
        dev, te = res.get("dev") or {}, res.get("test") or {}
        oos = (dev.get("oos") or {}).get("pooled")
        if not oos and not te.get("summary"):
            return None

        def sp(r):
            return None if not r else {"n": r.get("n"), "expectancy_r": _f(r.get("exp_r")), "ci95": r.get("ci95")}
        main = te.get("summary") or oos
        return {"expectancy_r": _f(main.get("exp_r")), "ci95": main.get("ci95"),
                "p_vs_random": te.get("p_vs_random") if te.get("summary") else (dev.get("oos") or {}).get("p_vs_random"),
                "max_dd_r": main.get("maxdd_r"), "trades": main.get("n"),
                "splits": {"dev": sp(oos), "val": None, "test": sp(te.get("summary"))},
                "dsr": dev.get("dsr"), "pbo": dev.get("pbo"), "gross_exp_r": dev.get("oos_gross_exp_r"),
                "scope_note": "dev = walk-forward ngoài mẫu (tham số chọn theo từng năm chỉ bằng dữ liệu trước đó, có embargo); test = khoá, mở tối đa 1 lần."}

    def scenario_info(self, st: dict, audience: str) -> dict:
        sc, res = st["scenario"], st.get("result") or {}
        sid = st["id"]
        info = {"phase": st.get("phase"), "side": sc.get("side"), "symbols": sc.get("symbols"), "tfs": sc.get("tfs"),
                "rules": (sc.get("detector") or {}).get("rules"), "levels": sc.get("levels"), "golden": sc.get("golden"),
                "family": sc.get("family"), "family_trials": self.store.family_size(sc.get("family", sid)) if self.store else 1,
                "detector": res.get("detector"), "dev": {k: v for k, v in (res.get("dev") or {}).items() if k != "ledger"},
                "test": res.get("test"), "test_opened": bool(self.store and self.store.test_opened(sid)),
                "meta": self.store.meta(sid) if self.store else {}}
        if audience == "master":
            info["images"] = [{"name": n, "url": f"/v1/ai-trading/scenarios/{sid}/images/{n}"} for n in (sc.get("images") or [])
                              if self.store and self.store.image(sid, n)]
        return info

    def warnings(self) -> list[str]:
        w = []
        s = self.load()["summary"]
        if s:
            ag = next((r for r in s["rows"] if r["label"].startswith("Test")), None)
            dv = next((r for r in s["rows"] if r["label"].startswith("Dev + Val")), None)
            if dv and ag:
                w.append(f"Kịch bản Sell KB-1..KB-4: {s.get('verdict', '')} - walk-forward ngoài mẫu {_vi(dv['exp_r'], '+.3f')} R/lệnh (n={dv['n']}), "
                         f"tập test khoá {_vi(ag['exp_r'], '+.3f')} R/lệnh (n={ag['n']}, p so với vào lệnh ngẫu nhiên = {_vi(ag['p_random'], '.2f')}).")
            else:
                w.append(str(s.get("verdict", "")))
        w.append("Chỉ nghiên cứu và mô phỏng (paper): hệ thống không đặt lệnh thật; giao dịch thật cần qua cổng pháp lý G1-G3 và duyệt của người dùng.")
        return w
