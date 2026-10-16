from __future__ import annotations

from datetime import date, timedelta

import pytest

D = date(2026, 10, 9)


def row(code, floor="HOSE", kind="STOCK", close=50_000.0, basic=50_000.0, pct=0.0, volume=100_000.0, value=5e9, industry="Ngân hàng",
        vn30=False, vn100=True, hnx30=False, mcap=1e13, pe=12.0, pb=2.0, f_net=0.0, ceil=None, flr=None, focus=True, **kw):
    band = {"HOSE": 0.07, "HNX": 0.10, "UPCOM": 0.15}[floor]
    r = {"code": code, "floor": floor, "kind": kind, "name": f"CTCP {code}", "short_name": code, "industry_code": 11, "industry_name": industry,
         "in_vn30": vn30, "in_vn100": vn100, "in_hnx30": hnx30, "focus": focus, "d": D, "basic": basic, "ceil": ceil or round(basic * (1 + band), -1),
         "flr": flr or round(basic * (1 - band), -1), "open": basic, "high": close, "low": close, "close": close, "ad_close": close, "volume": volume,
         "value": value, "pt_volume": 0.0, "pt_value": 0.0, "pct": pct, "marketcap": mcap, "pe": pe, "pb": pb, "ps": 2.0, "div_yield": 0.03, "beta": 1.0,
         "bvps": 20_000.0, "chg_1m": 0.02, "chg_3m": 0.05, "chg_6m": 0.1, "chg_1y": 0.2, "hi_52w": 60_000.0, "lo_52w": 40_000.0, "ratio_as_of": D,
         "f_buy": 1e9, "f_sell": 1e9 - f_net, "f_net": f_net, "f_net_vol": 0.0, "total_room": 1e9, "current_room": 6e8}
    r.update(kw)
    return r


def sample_rows():
    return [
        row("VCB", close=61_000, basic=60_000, pct=1.67, value=9e10, vn30=True, mcap=5e14, f_net=2e10),
        row("BID", close=44_000, basic=44_000, pct=0.0, value=3e10, vn30=True, mcap=2e14, f_net=-5e9),
        row("HPG", close=25_000, basic=26_000, pct=-3.85, value=8e10, industry="Thép", vn30=True, mcap=1.5e14, f_net=-3e10, pe=15, pb=1.6),
        row("VNM", close=57_700, basic=57_900, pct=-0.35, value=7e10, industry="Thực phẩm - Đồ uống", vn30=True, mcap=1.2e14, f_net=-2.4e9),
        row("TLH", close=9_680, basic=9_050, pct=6.96, value=2e9, industry="Thép", vn100=False, mcap=1e12, ceil=9_680, focus=False),   # trần
        row("PDV", close=8_420, basic=9_050, pct=-6.96, value=1e9, industry="Vận tải - kho bãi", vn100=False, mcap=8e11, flr=8_420, focus=False),  # sàn
        row("SHS", floor="HNX", close=15_000, basic=14_000, pct=7.14, value=4e10, industry="Chứng khoán", vn100=False, hnx30=True, mcap=4e12, f_net=1e10),
        row("ABC", floor="UPCOM", close=10_000, basic=10_000, pct=0.0, volume=0.0, value=0.0, industry="Khác", vn100=False, mcap=None, pe=None, pb=None, focus=False),
        row("E1VFVN30", kind="ETF", close=33_840, basic=34_000, pct=-0.47, value=1.5e10, industry="Quỹ ETF", vn100=False, mcap=None, pe=None, pb=None),
    ]


class FakeStore:
    """Cùng giao diện đọc với store.Store nhưng dữ liệu cố định."""

    def __init__(self):
        self.rows = sample_rows()
        self.meta = {}
        self.tables: dict[str, list[dict]] = {}

    async def latest_date(self): return D
    async def snapshot(self, d): return self.rows if d == D else []
    async def index_on(self, d):
        return [{"code": "VNINDEX", "d": D, "close": 1735.09, "chg": -3.88, "pct": -0.223, "open": 1737.6, "high": 1744.9, "low": 1724.2, "volume": 7.4e8,
                 "value": 1.47e13, "pt_value": 1.2e13, "advances": 121, "declines": 170, "no_change": 63, "no_trade": 40, "ceiling_n": 9, "floor_n": 5, "kind": "COMPOSITE", "floor": "HOSE"},
                {"code": "VN30", "d": D, "close": 1873.4, "chg": -3.5, "pct": -0.19, "advances": 11, "declines": 15, "no_change": 4, "no_trade": 0, "ceiling_n": 0, "floor_n": 0}]
    async def index_series(self, code, n):
        return [{"code": code, "d": D - timedelta(days=i), "close": 1700 + i, "advances": 100 + i, "declines": 150, "no_change": 50, "ceiling_n": 5, "floor_n": 3, "pct": 0.1}
                for i in range(min(n, 30) - 1, -1, -1)]
    async def liquidity_series(self, n):
        out = []
        for i in range(min(n, 25) - 1, -1, -1):
            for fl, v in (("HOSE", 1.4e13), ("HNX", 1e12), ("UPCOM", 5e11)):
                out.append({"d": D - timedelta(days=i), "floor": fl, "value": v * (1.5 if i == 0 else 1.0), "pt_value": 1e11, "volume": 1e8, "traded": 300})
        return out
    async def trading_dates(self, n): return [D - timedelta(days=i) for i in range(n)]
    async def foreign_market_series(self, n): return [{"d": D, "floor": "HOSE", "buy_val": 5e12, "sell_val": 6e12, "net_val": -1e12}]
    async def foreign_cum(self, since): return [{"code": "VCB", "net_val": 5e10, "buy_val": 1e11, "sell_val": 5e10, "days": 5},
                                                {"code": "HPG", "net_val": -9e10, "buy_val": 1e10, "sell_val": 1e11, "days": 5}]
    async def closes(self, codes, since):
        out = []
        for c in codes:
            for i in range(60):
                out.append({"code": c, "d": D - timedelta(days=60 - i), "ad_close": 100.0 + i * 0.5 + (i % 3), "close": 100.0 + i, "value": 1e9})
        return out
    async def symbols(self, focus_only=False):
        return [{k: r.get(k) for k in ("code", "floor", "kind", "name", "short_name", "industry_name", "in_vn30", "in_vn100", "in_hnx30", "focus")}
                for r in self.rows if r["focus"] or not focus_only]
    async def symbol_info(self, code):
        r = next((r for r in self.rows if r["code"] == code), None)
        return {k: r[k] for k in ("code", "floor", "kind", "name", "short_name", "industry_name", "marketcap", "pe", "pb")} if r else None
    async def history(self, code, n):
        return [{"code": code, "d": D - timedelta(days=i), "close": 50_000.0 + i, "ad_close": 50_000.0 + i, "open": 1, "high": 1, "low": 1, "volume": 1, "value": 1,
                 "basic": 1, "ceil": 1, "flr": 1, "pt_value": 0, "pct": 0.1} for i in range(min(n, 10) - 1, -1, -1)]
    async def foreign_series(self, code, n): return []
    async def events(self, start, end, codes=None):
        ev = [{"event_id": "1", "code": "VCB", "etype": "DIVIDEND", "type_desc": "Cổ tức bằng tiền", "note": "Trả cổ tức 1000 đ/cp", "dividend": 1000.0, "ratio": 10.0,
               "disclosure_date": D, "effective_date": D + timedelta(days=10), "expired_date": None, "actual_date": None, "name": "Vietcombank", "floor": "HOSE",
               "in_vn30": True, "in_vn100": True, "industry_name": "Ngân hàng"},
              {"event_id": "2", "code": "TLH", "etype": "ISSUE", "type_desc": "Phát hành thêm", "note": "x", "dividend": None, "ratio": None, "disclosure_date": D,
               "effective_date": D + timedelta(days=5), "expired_date": None, "actual_date": None, "name": "TLH", "floor": "HOSE", "in_vn30": False, "in_vn100": False,
               "industry_name": "Thép"}]
        return [e for e in ev if not codes or e["code"] in codes]
    async def news_recent(self, days, limit=600):
        return [{"url": "u1", "title": "VCB và HPG dẫn dắt thị trường", "summary": "", "source": "cafef", "lang": "vi", "published_at": None, "ingested_at": None},
                {"url": "u2", "title": "GDP quý III tăng 7%", "summary": "USD tăng", "source": "vnexpress", "lang": "vi", "published_at": None, "ingested_at": None},
                {"url": "u3", "title": "VCB TĂNG GIÁ MẠNH VÀ HPG GIẢM", "summary": "", "source": "x", "lang": "vi", "published_at": None, "ingested_at": None}]
    async def counts(self): return {"symbols": 9, "daily_rows": 9, "last_daily": D, "daily_dates": 1, "last_foreign": D, "last_ratio": D, "upcoming_events": 2}
    async def meta_get(self, k): return self.meta.get(k)
    async def meta_set(self, k, v): self.meta[k] = v
    async def close(self): pass


@pytest.fixture
def fake_store():
    return FakeStore()
