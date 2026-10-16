"""Báo cáo THEO TÀI KHOẢN (daily|weekly|monthly): hiệu suất, rủi ro, nhật ký, tuân thủ luật. CHỈ ĐỌC.

Quy ước kỳ (giờ VN): period = ngày (YYYY-MM-DD) CUỐI của kỳ.
  daily   = ngày `period` (00:00 -> 24:00);  weekly = 7 ngày kết thúc ở `period` (Thứ hai..Chủ nhật khi theo lịch);
  monthly = từ mùng 1 của tháng chứa `period` đến hết `period` (theo lịch: ngày cuối tháng).
Mục tuân thủ phụ thuộc auth nội bộ (có thể chưa deploy): lỗi/thiếu -> 'Chưa có dữ liệu', KHÔNG làm hỏng báo cáo.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from tscommon.sources import scrub_obj

from . import charts
from .build import num, pct_pts, pdt
from .collect import Gateway, Raw, iso
from .config import Settings

log = logging.getLogger("reporter.account")

KIND_VI = {"daily": "Báo cáo ngày", "weekly": "Báo cáo tuần", "monthly": "Báo cáo tháng"}
CODE = {"daily": "NGAY", "weekly": "TUAN", "monthly": "THANG"}
SECTION_TITLES = {"performance": "Hiệu suất", "risk": "Rủi ro", "journal": "Nhật ký giao dịch", "compliance": "Tuân thủ luật"}
ORDER = ["performance", "risk", "journal", "compliance"]
OPTIONAL = {"compliance"}           # thiếu không đánh dấu báo cáo 'degraded'
STATUS_VI = {"green": ("✓", "Đạt"), "yellow": ("!", "Gần ngưỡng"), "red": ("✕", "Vi phạm"), "na": ("—", "Chưa đánh giá")}
BUDGET_VI = {"ok": "Trong ngân sách", "warn": "Gần ngưỡng", "crit": "Vượt ngân sách", "na": "Chưa đủ dữ liệu", "no_position": "Không có vị thế"}


# ---------------- kỳ ----------------
def _month_end_prev(d: date) -> date:
    return d.replace(day=1) - timedelta(days=1)


def previous_period(kind: str, p: date) -> date:
    return p - timedelta(days=1) if kind == "daily" else p - timedelta(days=7) if kind == "weekly" else _month_end_prev(p)


def last_period(kind: str, now: datetime, tz: str) -> date:
    """Kỳ đã KẾT THÚC gần nhất theo lịch (daily: hôm qua; weekly: Chủ nhật vừa qua; monthly: ngày cuối tháng trước)."""
    today = now.astimezone(ZoneInfo(tz)).date()
    if kind == "daily":
        return today - timedelta(days=1)
    if kind == "weekly":
        return today - timedelta(days=((today.weekday() + 1) % 7) or 7)
    return _month_end_prev(today)


def due_period(kind: str, hour: int, now: datetime, tz: str) -> str:
    """Kỳ cần có tại thời điểm `now` cho lịch giờ `hour`: kỳ kết thúc gần nhất mà (ngày kế tiếp, `hour`:00 giờ VN) <= now."""
    z = ZoneInfo(tz)
    loc = now.astimezone(z)
    p = last_period(kind, now, tz)
    cut = datetime.combine(p + timedelta(days=1), datetime.min.time(), tzinfo=z) + timedelta(hours=hour)
    if loc < cut:
        p = previous_period(kind, p)
    return p.isoformat()


def window(kind: str, period: str, tz: str) -> tuple[datetime, datetime]:
    """(đầu, cuối-không-gồm) theo giờ VN."""
    z = ZoneInfo(tz)
    p = date.fromisoformat(period)
    start_d = p if kind == "daily" else p - timedelta(days=6) if kind == "weekly" else p.replace(day=1)
    mk = lambda d: datetime(d.year, d.month, d.day, tzinfo=z)  # noqa: E731
    return mk(start_d), mk(p + timedelta(days=1))


# ---------------- thu thập ----------------
class AuthClient:
    """Gọi auth nội bộ (Bearer FLEET_INTERNAL_TOKEN). Không token / lỗi -> ném ngoại lệ để caller xử lý thiếu-lịch-sự."""

    def __init__(self, url: str, token: str, client: httpx.AsyncClient | None = None, timeout: float = 10.0):
        self.url, self.token = url.rstrip("/"), token
        self._own = client is None
        self.client = client or httpx.AsyncClient(base_url=self.url, timeout=timeout, headers={"Authorization": f"Bearer {token}"} if token else {})

    async def aclose(self):
        if self._own:
            await self.client.aclose()

    async def get(self, path: str, params: dict | None = None):
        if not self.token:
            raise RuntimeError("chưa cấu hình FLEET_INTERNAL_TOKEN")
        r = await self.client.get(path, params=params)
        r.raise_for_status()
        return r.json()

    async def scope_accounts(self, type_: str, ref: str | None) -> list[dict]:
        d = await self.get("/internal/fleet/scope-accounts", {"type": type_, "ref": ref or ""})
        return [a for a in (d.get("accounts") or []) if isinstance(a, dict) and a.get("account_id")]


async def collect_account(cfg: Settings, gw: Gateway, auth: AuthClient | None, account_id: str, kind: str, period: str) -> Raw:
    raw = Raw()
    start, end = window(kind, period, cfg.tz)
    sem = asyncio.Semaphore(4)

    async def fetch(name: str, coro_fn):
        async with sem:
            try:
                raw.data[name] = await coro_fn()
            except Exception as e:  # noqa: BLE001
                raw.data[name] = None
                code = getattr(getattr(e, "response", None), "status_code", None)
                raw.errors[name] = f"HTTP {code}" if code else type(e).__name__
                log.warning("báo cáo tài khoản: nguồn %s lỗi (%s)", name, raw.errors[name])

    jobs = [
        fetch("risk", lambda: gw.get(f"/risk/accounts/{account_id}")),
        fetch("equity", lambda: gw.get("/equity-history", {"account_id": account_id, "from": iso(start), "to": iso(end), "limit": 5000})),
        fetch("journal", lambda: gw.get(f"/journal/{account_id}/summary", {"from": start.date().isoformat(), "to": period, "tz": cfg.tz})),
    ]
    if auth is not None:
        jobs.append(fetch("compliance", lambda: auth.get(f"/internal/fleet/account/{account_id}/compliance")))
    else:
        raw.data["compliance"] = None
        raw.errors["compliance"] = "chưa cấu hình"
    await asyncio.gather(*jobs)
    return raw


# ---------------- dựng ----------------
def _f(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _downsample(pts: list, n: int = 160) -> list:
    if len(pts) <= n:
        return pts
    step = (len(pts) - 1) / (n - 1)
    return [pts[round(i * step)] for i in range(n)]


def sec_performance(raw: Raw, cfg, kind) -> dict:
    d = raw.data.get("equity")
    if not isinstance(d, list):
        return {"ok": False, "error": "chưa đọc được lịch sử equity"}
    pts = [(pdt(p.get("ts")), _f(p.get("equity")), _f(p.get("balance"))) for p in d if isinstance(p, dict)]
    pts = sorted((t, e, b) for t, e, b in pts if t is not None and e is not None and e > 0)
    if not pts:
        return {"ok": False, "error": "chưa có điểm equity trong kỳ"}
    eq = [e for _, e, _ in pts]
    peak, mdd, mdd_pct, dd_series = eq[0], 0.0, 0.0, []
    for e in eq:
        peak = max(peak, e)
        dd = peak - e
        ddp = dd / peak * 100 if peak else 0.0
        dd_series.append(-ddp)
        if dd > mdd:
            mdd = dd
        mdd_pct = max(mdd_pct, ddp)
    first, last = pts[0], pts[-1]
    pnl = last[1] - first[1]
    bal = [b for _, _, b in pts if b is not None]
    return {
        "n_points": len(pts), "start_equity": num(first[1]), "end_equity": num(last[1]), "pnl": f"{pnl:+,.2f}", "pnl_up": pnl >= 0,
        "pnl_pct": pct_pts(pnl / first[1] * 100 if first[1] else None), "high": num(max(eq)), "low": num(min(eq)),
        "start_balance": num(bal[0]) if bal else "—", "end_balance": num(bal[-1]) if bal else "—",
        "max_dd": num(mdd), "max_dd_pct": f"{mdd_pct:.2f}%",
        "first_ts": first[0].astimezone(ZoneInfo(cfg.tz)).strftime("%d/%m %H:%M"), "last_ts": last[0].astimezone(ZoneInfo(cfg.tz)).strftime("%d/%m %H:%M"),
        "_eq": [round(x, 2) for x in _downsample(eq)], "_dd": [round(x, 3) for x in _downsample(dd_series)],
    }


def sec_risk(raw: Raw, cfg, kind) -> dict:
    d = raw.data.get("risk")
    if not isinstance(d, dict) or not d.get("account"):
        return {"ok": False, "error": "chưa đọc được dữ liệu rủi ro"}
    a, mg, ex = d["account"], d.get("margin") or {}, d.get("exposure") or {}
    dd, var, bud = d.get("drawdown") or {}, d.get("var") or {}, d.get("budget") or {}
    ddok = bool(dd.get("available"))
    var95 = ((var.get("hist") or {}).get("95") or {}).get("var_pct") if var.get("available") else None
    es = ((var.get("hist") or {}).get("es") or {}).get("es_pct") if var.get("available") else None
    syms = [{"symbol": s.get("symbol"), "net_lots": num(s.get("net_lots"), 2), "pct_eq": pct_pts(s["net_value"] / a["equity"] * 100) if a.get("equity") and s.get("net_value") is not None else "—",
             "pnl": f"{(s.get('pnl') or 0):+,.2f}"} for s in (ex.get("by_symbol") or [])[:8]]
    items = [{"label": i.get("label"), "unit": i.get("unit") or "", "value": num(i.get("value")), "limit": num(i.get("limit")),
              "status": i.get("status"), "_used": (i["used_pct"] / 100.0 if i.get("used_pct") is not None else None)} for i in (bud.get("items") or [])]
    bstat = bud.get("status") or "na"
    return {
        "currency": a.get("currency") or "", "equity": num(a.get("equity")), "balance": num(a.get("balance")),
        "margin_level": "—" if mg.get("margin_level_pct") is None else f"{mg['margin_level_pct']:,.0f}%",
        "margin_used": num(mg.get("margin_used")), "free_margin": num(mg.get("free_margin")),
        "margin_status": BUDGET_VI.get(mg.get("status") or "", mg.get("status") or "—"),
        "leverage": num(ex.get("leverage_gross"), 2), "positions": ex.get("positions") or 0, "ccy_conc": pct_pts(ex.get("max_ccy_conc_pct"), 1),
        "day_pnl": pct_pts(dd["day"]["pnl_pct"]) if ddok and (dd.get("day") or {}).get("pnl_pct") is not None else "—",
        "dd_peak": pct_pts(dd.get("dd_from_peak_pct")) if ddok else "—", "max_dd_hist": pct_pts(dd.get("max_dd_pct")) if ddok else "—",
        "var95": pct_pts(var95), "es": pct_pts(es), "by_symbol": syms, "budget": items, "budget_status": bstat,
        "budget_vi": BUDGET_VI.get(bstat, bstat), "warnings": [str(w) for w in (d.get("warnings") or [])][:6],
        "as_of": (a.get("ts") or "")[:16].replace("T", " "),
    }


def sec_journal(raw: Raw, cfg, kind) -> dict:
    d = raw.data.get("journal")
    if not isinstance(d, dict) or not isinstance(d.get("summary"), dict):
        return {"ok": False, "error": "chưa đọc được nhật ký giao dịch"}
    s = d["summary"]
    if not s.get("n"):
        return {"empty": True, "empty_msg": "Không có lệnh đã đóng trong kỳ."}
    jn = lambda v, k=2: "—" if v is None else f"{v:+,.{k}f}"  # noqa: E731
    sym = [(str(r.get("key")), _f(r.get("net"))) for r in ((d.get("groups") or {}).get("symbol") or [])[:10]]
    rows = [{"symbol": r.get("key"), "n": r.get("n"), "net": jn(_f(r.get("net"))), "wr": "—" if r.get("win_rate") is None else f"{r['win_rate'] * 100:.0f}%",
             "pf": num(r.get("profit_factor"))} for r in ((d.get("groups") or {}).get("symbol") or [])[:10]]
    return {"empty": False, "n": s["n"], "wins": s.get("wins", 0), "losses": s.get("losses", 0), "breakeven": s.get("breakeven", 0),
            "wr": "—" if s.get("win_rate") is None else f"{s['win_rate'] * 100:.0f}%", "net": jn(s.get("net")), "net_up": (s.get("net") or 0) >= 0,
            "pf": num(s.get("profit_factor")), "exp": jn(s.get("expectancy")), "avg_win": num(s.get("avg_win")), "avg_loss": num(s.get("avg_loss")),
            "best": jn(s.get("best")), "worst": jn(s.get("worst")), "loss_streak": (d.get("streaks") or {}).get("max_loss_streak", 0),
            "by_symbol": rows, "_sym": sym}


def sec_compliance(raw: Raw, cfg, kind) -> dict:
    d = raw.data.get("compliance")
    if not isinstance(d, dict) or not isinstance(d.get("rules"), list):
        return {"ok": False, "error": "chưa có dữ liệu luật tuân thủ"}
    rules, cnt = [], {"green": 0, "yellow": 0, "red": 0, "na": 0}
    for r in d["rules"]:
        if not isinstance(r, dict):
            continue
        st = r.get("status") if r.get("status") in cnt else "na"
        cnt[st] += 1
        up = _f(r.get("usage_pct"))
        rules.append({"name": r.get("rule_name") or r.get("name") or "Luật", "status": st, "glyph": STATUS_VI[st][0], "status_vi": STATUS_VI[st][1],
                      "value": num(_f(r.get("value"))), "limit": num(_f(r.get("limit"))), "unit": r.get("unit") or "",
                      "headroom": num(_f(r.get("headroom"))), "_used": None if up is None else up / 100.0})
    if not rules:
        return {"empty": True, "counts": cnt, "rules": []}
    return {"empty": False, "counts": cnt, "rules": rules}


def has_data(raw: Raw) -> bool:
    """Có ít nhất một nguồn lõi trả dữ liệu thật (equity trong kỳ / lệnh đóng / rủi ro)."""
    eq = raw.data.get("equity")
    if isinstance(eq, list) and any(isinstance(p, dict) and (_f(p.get("equity")) or 0) > 0 for p in eq):
        return True
    j = raw.data.get("journal")
    if isinstance(j, dict) and (j.get("summary") or {}).get("n"):
        return True
    r = raw.data.get("risk")
    return bool(isinstance(r, dict) and (r.get("account") or {}).get("equity"))


def summary_lines(kind: str, sec: dict) -> list[str]:
    L = []
    p = sec["performance"]
    L.append(f"Hiệu suất kỳ: {p['pnl']} ({p['pnl_pct']}), equity cuối {p['end_equity']}, sụt giảm tối đa {p['max_dd_pct']}." if p.get("ok")
             else "Hiệu suất: chưa có dữ liệu equity trong kỳ.")
    j = sec["journal"]
    L.append("Nhật ký: không có lệnh đóng trong kỳ." if j.get("ok") and j.get("empty") else
             f"Nhật ký: {j['n']} lệnh, tỷ lệ thắng {j['wr']}, lãi/lỗ ròng {j['net']}, hệ số lợi nhuận {j['pf']}." if j.get("ok") else "Nhật ký: chưa có dữ liệu.")
    r = sec["risk"]
    L.append(f"Rủi ro: ngân sách {r['budget_vi'].lower()}, margin level {r['margin_level']}, đòn bẩy hiệu dụng {r['leverage']}x." if r.get("ok") else "Rủi ro: chưa có dữ liệu.")
    c = sec["compliance"]
    if c.get("ok") and not c.get("empty"):
        n = c["counts"]
        L.append(f"Tuân thủ: {n['green']} đạt, {n['yellow']} gần ngưỡng, {n['red']} vi phạm.")
    else:
        L.append("Tuân thủ luật: chưa có dữ liệu.")
    return L


def build_account(kind: str, period: str, account_id: str, label: str | None, raw: Raw, cfg: Settings, now: datetime) -> dict:
    def _sec(fn):
        try:
            r = fn(raw, cfg, kind)
            r = r if isinstance(r, dict) else {}
            r.setdefault("ok", True)
            return r
        except Exception as e:  # noqa: BLE001
            log.exception("mục lỗi")
            return {"ok": False, "error": f"lỗi xử lý ({type(e).__name__})"}

    sec = {"performance": _sec(sec_performance), "risk": _sec(sec_risk), "journal": _sec(sec_journal), "compliance": _sec(sec_compliance)}
    start, end = window(kind, period, cfg.tz)
    loc = now.astimezone(ZoneInfo(cfg.tz))
    risk_acc = ((raw.data.get("risk") or {}).get("account") or {}) if isinstance(raw.data.get("risk"), dict) else {}
    ctx = {
        "kind": kind, "kind_vi": KIND_VI[kind], "period": period, "code": f"{CODE[kind]}-{period}-{account_id}",
        "account": {"id": account_id, "label": label or risk_acc.get("name") or "", "platform": (risk_acc.get("platform") or "").upper(),
                    "currency": risk_acc.get("currency") or ""},
        "generated_utc": now.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "generated_vn": loc.strftime("%d/%m/%Y %H:%M") + " (giờ VN)",
        "window": f"{start.strftime('%d/%m/%Y')} → {(end - timedelta(days=1)).strftime('%d/%m/%Y')} (giờ VN)",
        "sections": sec, "order": ORDER, "titles": SECTION_TITLES, "summary": summary_lines(kind, sec),
        "ok": [k for k in ORDER if sec[k].get("ok")], "fail": [k for k in ORDER if not sec[k].get("ok") and k not in OPTIONAL],
    }
    ctx = scrub_obj(ctx, drop_keys=False)           # lớp 1: lọc tên nguồn trước khi dựng SVG (Markup không bị scrub làm mất tính an toàn)
    s = ctx["sections"]
    if s["performance"].get("ok"):
        p = s["performance"]
        p["chart"] = charts.sparkline(p.pop("_eq"), w=640, h=110, title="Đường equity")
        p["dd_chart"] = charts.sparkline(p.pop("_dd"), w=640, h=60, title="Sụt giảm từ đỉnh (%)")
    if s["journal"].get("ok") and not s["journal"].get("empty"):
        j = s["journal"]
        j["sym_chart"] = charts.hbar(j.pop("_sym"), unit="", digits=2, w=560)
    if s["risk"].get("ok"):
        for i in s["risk"]["budget"]:
            i["meter"] = charts.meter(i.pop("_used"), label=str(i.get("label") or ""))
    if s["compliance"].get("ok"):
        for i in s["compliance"]["rules"]:
            i["meter"] = charts.meter(i.pop("_used"), label=str(i.get("name") or ""))
    return ctx
