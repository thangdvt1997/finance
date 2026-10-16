"""Giai đoạn C2: regime (hiện vật nghiên cứu offline) + đồng thuận chuyên gia (track-record) + ngữ cảnh cho AI analyst.
READ-ONLY: chỉ đọc JSON hiện vật và GET nội bộ; không có đường đặt lệnh. Không tên nguồn dữ liệu trong đầu ra."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Callable

from fastapi import FastAPI, HTTPException, Query
from tscommon.sources import has_source_name, scrub_sources

log = logging.getLogger("ai-trading.c2")
SYM = r"^[A-Za-z0-9][A-Za-z0-9:_.\-]{0,23}$"
Aud = Annotated[str, Query(pattern=r"^(master|client)$")]
Sym = Annotated[str, Query(pattern=SYM)]
REGIME_NOTE = ("Regime = trạng thái biến động/xu hướng đã quan sát, KHÔNG phải dự báo hướng giá. Mô hình dự báo được biến động ngắn hạn kế tiếp (ở mức thống kê yếu-vừa) "
               "nhưng không hơn đường cơ sở đơn giản, và không có bằng chứng dự báo hướng. Dùng để điều chỉnh rủi ro/bật-tắt kịch bản; chỉ nghiên cứu/paper.")
CONS_NOTE = ("Đồng thuận chủ yếu là đếm phiếu của các nguồn chưa đủ mẫu; sau hiệu chỉnh đa kiểm định không nguồn nào vượt ngẫu nhiên. "
             "Dùng như đặc trưng tham khảo, không phải tín hiệu giao dịch.")


def _vi(x, d=2):
    return "n/a" if x is None else f"{x:.{d}f}".replace(".", ",")


class C2:
    def __init__(self, regime_dir: str, track_url: str, scan: Callable, hdrs: Callable[[], dict], get=None):
        self.dir, self.track, self.scan, self.hdrs = Path(regime_dir), track_url, scan, hdrs
        self._get = get or self._http_get
        self._mt: tuple | None = None
        self._reg: dict | None = None
        self._cache: dict[str, tuple[float, object]] = {}

    # ---------- regime ----------
    def regime_doc(self) -> dict | None:
        f = self.dir / "summary.json"
        try:
            sig = (f.stat().st_mtime_ns, f.stat().st_size)
        except OSError:
            return None
        if sig != self._mt:
            try:
                self._reg, self._mt = json.loads(f.read_text(encoding="utf-8")), sig
            except (OSError, ValueError):
                return None
        return self._reg

    def regime_symbol(self, sym: str, audience: str) -> dict | None:
        d = self.regime_doc()
        if not d:
            return None
        r = next((x for x in d["symbols"] if x["symbol"] == sym.upper() and "current" in x), None)
        if not r:
            return None
        cur = r["current"]
        out = {"symbol": r["symbol"], "current": {k: cur[k] for k in ("as_of", "label", "prob", "days_in_state", "ann_vol_pct", "trend", "vol_percentile")}}
        if audience == "master":
            out["current"].update({"trend_t20": cur["trend_t20"], "kmeans_label": cur["kmeans_label"]})
            out["states_fit"], out["eval"] = r["states_fit"], r["eval"]
            out["history"] = {"first_day": r["first_day"], "fit_days": r["fit_days"], "holdout_days": r["holdout_days"], "val_days": r["val_days"]}
        return out

    def regime_all(self, audience: str) -> dict:
        d = self.regime_doc()
        if not d:
            return {"available": False, "symbols": [], "note": REGIME_NOTE}
        syms = [self.regime_symbol(x["symbol"], audience) for x in d["symbols"] if "current" in x]
        out = {"available": True, "generated_at": d["generated_at"], "method": d["method"], "symbols": [s for s in syms if s], "note": REGIME_NOTE,
               "verdict": {"summary": d["verdict"]["summary_vi"]}, "missing": d.get("missing", [])}
        if audience == "master":
            out["verdict"].update({k: v for k, v in d["verdict"].items() if k != "summary_vi"})
            out["locks"], out["horizon_days"] = d["locks"], d["horizon_days"]
        return out

    # ---------- consensus ----------
    def _http_get(self, path: str) -> dict | None:
        req = urllib.request.Request(self.track + path, headers={"Accept": "application/json", **self.hdrs()})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 (URL nội bộ từ cấu hình, chỉ GET)
                return json.loads(r.read(4_000_000))
        except Exception as e:  # noqa: BLE001
            log.warning("track-record không khả dụng: %s", type(e).__name__)
            return None

    async def _cached(self, key: str, path: str, ttl: float = 60):
        t = self._cache.get(key)
        if t and time.monotonic() - t[0] < ttl:
            return t[1]
        v = await asyncio.to_thread(self._get, path)
        if v is not None:
            self._cache[key] = (time.monotonic(), v)
        return v

    async def consensus(self, symbol: str | None, audience: str) -> dict:
        c = await self._cached("cons", "/track/consensus?window_days=14&scope=all&min_experts=1")
        lb = await self._cached("lb", "/track/leaderboard?horizon=1W&scope=all&limit=200")
        if c is None or lb is None:
            raise HTTPException(503, "đồng thuận chưa khả dụng")
        s = lb.get("summary", {})
        rel = {"entities": s.get("entities"), "rated": s.get("rated"), "insufficient": s.get("insufficient"), "beating_baseline": s.get("beating_baseline"),
               "tier": "chưa chứng minh" if not s.get("beating_baseline") else "có nguồn vượt ngẫu nhiên",
               "text": (f"{s.get('rated')}/{s.get('entities')} nguồn đủ mẫu để xếp hạng; {s.get('beating_baseline')} nguồn vượt ngẫu nhiên sau hiệu chỉnh đa kiểm định (FDR 10%).")}
        out = {"as_of": c.get("as_of"), "window_days": c.get("window_days"), "reliability": rel, "note": CONS_NOTE}
        rows = c.get("rows", [])

        def feat(r):
            n = r["n_experts"]
            top = r.get("top", [])
            rated_top = sum(1 for t in top if t.get("status") == "rated")
            f = {"symbol": r["symbol"], "n_experts": n, "bullish": r["bullish"]["n"], "bearish": r["bearish"]["n"], "net_weighted": r["net_weighted"],
                 "agreement": r["agreement"], "level": r["level"], "latest_at": r.get("latest_at"),
                 "confidence": "thấp" if (n < 3 or rated_top == 0) else "vừa"}
            f["feature_vector"] = [r["net_weighted"], r["agreement"], min(n, 50) / 50.0, rated_top / max(1, len(top))]
            return f
        if symbol:
            r = next((x for x in rows if x["symbol"] == symbol.upper()), None)
            out["symbol"] = feat(r) if r else None
            if r and audience == "master":
                out["symbol"]["top"] = [{"label": t["label"], "direction": t["direction"], "status": t["status"], "weight": t["weight"]}
                                        for t in r.get("top", []) if not has_source_name(t.get("label", ""))][:5]
        else:
            out["rows"] = [feat(r) for r in rows[:60]]
            if audience == "master":
                out["rated_experts"] = [{"label": x["label"], "kind": x["kind"], "n": x["n"], "hit_rate": x["hit_rate"], "q_value": x["q_value"], "beats_baseline": x["beats_baseline"]}
                                        for x in lb.get("rows", []) if x.get("status") == "rated" and not has_source_name(x.get("label", ""))][:12]
        return out

    # ---------- ngữ cảnh cho AI analyst (nội bộ: chỉ briefing gọi) ----------
    async def analyst_context(self, symbol: str) -> dict:
        setups = await self.scan(f"/scan/setups?view=active&symbol={urllib.parse.quote(symbol.upper())}&limit=8&audience=master")
        sc = []
        for i in (setups or {}).get("items", [])[:6]:
            sc.append({"pattern": i.get("pattern"), "name": i.get("name"), "tf": i.get("tf"), "side": i.get("side"), "state": i.get("state"),
                       "bar_ts": i.get("bar_ts"), "steps": [{"ok": bool(s.get("ok")), "label": s.get("label"), "detail": s.get("detail")} for s in i.get("steps", [])]})
        try:
            cons = (await self.consensus(symbol, "client")).get("symbol")
        except HTTPException:
            cons = None
        return {"symbol": symbol.upper(), "regime": self.regime_symbol(symbol, "client"), "consensus": cons, "scenarios": sc,
                "generated_at": datetime.now(timezone.utc).isoformat()}


def register(app: FastAPI, st, scan: Callable, hdrs: Callable[[], dict], get=None) -> C2:
    c2 = C2(st.regime_dir, st.track_url, scan, hdrs, get)
    app.state.c2 = c2

    @app.get("/ai/regime", tags=["ai-trading"])
    async def regime(audience: Aud = "master", symbol: Annotated[str | None, Query(pattern=SYM)] = None):
        if symbol:
            r = c2.regime_symbol(symbol, audience)
            if not r:
                raise HTTPException(404, "không có regime cho mã này")
            return {**r, "note": REGIME_NOTE}
        return c2.regime_all(audience)

    @app.get("/ai/consensus", tags=["ai-trading"])
    async def consensus(audience: Aud = "master", symbol: Annotated[str | None, Query(pattern=SYM)] = None):
        return await c2.consensus(symbol, audience)

    @app.get("/ai/analyst-context", tags=["ai-trading"])
    async def analyst_context(symbol: Sym):
        return await c2.analyst_context(symbol)

    return c2
