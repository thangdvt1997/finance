from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

Row = dict[str, Any]
TF_ORDER = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]
_MIN = datetime.min.replace(tzinfo=timezone.utc)


class Repo(Protocol):
    """Lớp truy vấn chỉ ĐỌC. Có bản Postgres (pg_repo) và in-memory (cho test)."""

    async def ping(self) -> bool: ...
    async def bars(self, symbol: str, tf: str, start: datetime | None, end: datetime | None,
                   order: str, limit: int, offset: int) -> list[Row]: ...
    async def quotes_latest(self, symbols: list[str] | None, limit: int) -> list[Row]: ...
    async def news(self, symbol: str | None, since: datetime | None, limit: int, offset: int) -> list[Row]: ...
    async def calendar(self, start: datetime | None, end: datetime | None, impact: list[str] | None,
                       limit: int, offset: int, order: str = "upcoming", now: datetime | None = None) -> list[Row]:
        """order: upcoming (sắp tới tăng dần trước, rồi quá khứ mới->cũ) | asc | desc."""
        ...
    async def experts(self, limit: int, offset: int) -> list[Row]: ...
    async def expert_signals(self, symbol: str | None, status: str | None, expert_id: str | None,
                             limit: int, offset: int) -> list[Row]: ...
    async def expert_positions(self, symbol: str | None, expert_id: str | None, limit: int, offset: int) -> list[Row]: ...
    async def expert_opinions(self, group: str | None, stance: str | None, symbol: str | None, expert_id: str | None,
                              limit: int, offset: int) -> list[Row]:
        """Y kien chuyen gia (bang expert_opinions, migration 017); chua co bang -> []."""
        return []
    async def accounts_latest(self) -> list[Row]: ...
    async def account_orders(self, account_id: str, status: str, limit: int) -> list[Row]:
        """Lệnh chờ của 1 tài khoản (status: open|removed|all), mới nhất trước."""
        ...
    async def alerts(self, level: str | None, limit: int, offset: int) -> list[Row]: ...
    async def symbols(self) -> list[Row]:
        """[{symbol, tfs[], last_bar, last_quote}] cho symbol có bars hoặc quotes."""
        ...
    async def price_snapshot(self) -> dict[str, Any]:
        """{"quotes": {symbol: {ts,bid,ask}}, "d1": {symbol: [{ts_open,c}] giam dan, toi da 3 nen D1 gan nhat}} (cho /v1/symbols)."""
        ...
    async def equity_history(self, account_id: str, start: datetime | None, end: datetime | None,
                             limit: int) -> list[Row]:
        """[{ts, balance, equity, margin}] tăng dần theo ts (giữ `limit` điểm MỚI nhất trong khoảng)."""
        ...
    async def freshness(self) -> list[Row]:
        """[{name, last_ts, count_24h}] độ mới của từng bảng dữ liệu."""
        ...
    async def analytics(self, kind: str, symbol: str | None = None, key: str | None = None) -> list[Row]:
        """[{kind, key, ts, payload(dict), updated_at}] từ bảng analytics_snapshots (service analytics ghi)."""
        ...


def _page(rows: list[Row], limit: int, offset: int) -> list[Row]:
    return rows[offset: offset + limit]


class InMemoryRepo:
    """Dữ liệu nằm trong list; dùng cho test/dev. Sắp xếp giống bản SQL."""

    def __init__(self, **tables: list[Row]):
        self.t: dict[str, list[Row]] = {k: list(v) for k, v in tables.items()}

    def _tab(self, name: str) -> list[Row]:
        return self.t.get(name, [])

    async def ping(self) -> bool:
        return True

    async def bars(self, symbol, tf, start, end, order, limit, offset):
        rows = [r for r in self._tab("bars") if r["symbol"] == symbol and r["tf"] == tf
                and (start is None or r["ts_open"] >= start) and (end is None or r["ts_open"] <= end)]
        rows.sort(key=lambda r: r["ts_open"], reverse=(order == "desc"))
        return _page(rows, limit, offset)

    async def quotes_latest(self, symbols, limit):
        latest: dict[str, Row] = {}
        for r in self._tab("quotes"):
            if symbols and r["symbol"] not in symbols:
                continue
            cur = latest.get(r["symbol"])
            if cur is None or r["ts"] > cur["ts"]:
                latest[r["symbol"]] = r
        return sorted(latest.values(), key=lambda r: r["symbol"])[:limit]

    async def news(self, symbol, since, limit, offset):
        rows = [r for r in self._tab("news_items") if (symbol is None or symbol in (r.get("symbols") or []))
                and (since is None or ((r.get("published_at") or r.get("ingested_at") or _MIN) >= since))]
        # bo trung hien thi giong PgRepo.news: (tieu de chuan hoa, ngay) -> uu tien nguon tin, roi ban som nhat
        best: dict = {}
        for r in sorted(rows, key=lambda r: (str(r.get("source") or "").startswith("expert:"), r.get("published_at") or r.get("ingested_at") or _MIN, r["url"])):
            ts = r.get("published_at") or r.get("ingested_at")
            best.setdefault((" ".join(re.sub(r"\W+", " ", (r.get("title") or "").lower()).split()), ts.date() if ts else None), r)
        rows = list(best.values())
        rows.sort(key=lambda r: r.get("published_at") or r.get("ingested_at") or _MIN, reverse=True)
        return _page(rows, limit, offset)

    async def calendar(self, start, end, impact, limit, offset, order="upcoming", now=None):
        rows = [r for r in self._tab("calendar_events") if (start is None or r["ts"] >= start)
                and (end is None or r["ts"] <= end) and (not impact or r.get("impact") in impact)]
        if order == "asc":
            rows.sort(key=lambda r: r["ts"])
        elif order == "desc":
            rows.sort(key=lambda r: r["ts"], reverse=True)
        else:
            now = now or datetime.now(timezone.utc)
            up = sorted((r for r in rows if r["ts"] >= now), key=lambda r: r["ts"])
            past = sorted((r for r in rows if r["ts"] < now), key=lambda r: r["ts"], reverse=True)
            rows = up + past
        return _page(rows, limit, offset)

    async def experts(self, limit, offset):
        return _page(sorted(self._tab("experts"), key=lambda r: r["expert_id"]), limit, offset)

    async def expert_signals(self, symbol, status, expert_id, limit, offset):
        rows = [r for r in self._tab("expert_signals") if (symbol is None or r["symbol"] == symbol)
                and (status is None or r.get("status") == status) and (expert_id is None or r["expert_id"] == expert_id)]
        rows.sort(key=lambda r: r["opened_at"], reverse=True)
        return _page(rows, limit, offset)

    async def expert_positions(self, symbol, expert_id, limit, offset):
        rows = [r for r in self._tab("expert_positions") if (symbol is None or r["symbol"] == symbol)
                and (expert_id is None or r["expert_id"] == expert_id)]
        rows.sort(key=lambda r: r["as_of"], reverse=True)
        return _page(rows, limit, offset)

    async def accounts_latest(self):
        latest: dict[str, Row] = {}
        for r in self._tab("account_snapshots"):
            cur = latest.get(r["account_id"])
            if cur is None or r["ts"] > cur["ts"]:
                latest[r["account_id"]] = r
        out = []
        for r in sorted(latest.values(), key=lambda r: r["account_id"]):
            od = [o for o in self._tab("account_orders") if o["account_id"] == r["account_id"] and o.get("status", "open") == "open"]
            out.append({**r, "orders": [{k: o.get(k) for k in ("order_id", "symbol", "kind", "volume", "price", "sl", "tp", "time_setup")} for o in od]})
        return out

    async def account_orders(self, account_id, status, limit):
        rows = [o for o in self._tab("account_orders") if o["account_id"] == account_id
                and (status == "all" or o.get("status", "open") == status)]
        rows.sort(key=lambda o: (o.get("status", "open") != "open", -(o["time_setup"].timestamp() if o.get("time_setup") else 0)))
        return rows[:limit]

    async def alerts(self, level, limit, offset):
        rows = [r for r in self._tab("alerts") if level is None or r["level"] == level]
        rows.sort(key=lambda r: r["ts"], reverse=True)
        return _page(rows, limit, offset)

    async def symbols(self):
        out: dict[str, Row] = {}
        for r in self._tab("bars"):
            o = out.setdefault(r["symbol"], {"symbol": r["symbol"], "tfs": set(), "last_bar": None, "last_quote": None})
            o["tfs"].add(r["tf"])
            if o["last_bar"] is None or r["ts_open"] > o["last_bar"]:
                o["last_bar"] = r["ts_open"]
        for r in self._tab("quotes"):
            o = out.setdefault(r["symbol"], {"symbol": r["symbol"], "tfs": set(), "last_bar": None, "last_quote": None})
            if o["last_quote"] is None or r["ts"] > o["last_quote"]:
                o["last_quote"] = r["ts"]
        return [{**o, "tfs": sorted(o["tfs"], key=TF_ORDER.index)} for _, o in sorted(out.items())]

    async def price_snapshot(self):
        quotes = {r["symbol"]: r for r in await self.quotes_latest(None, 10_000)}
        d1: dict[str, list[Row]] = {}
        for r in sorted(self._tab("bars"), key=lambda r: r["ts_open"], reverse=True):
            if r["tf"] == "D1" and len(d1.setdefault(r["symbol"], [])) < 3:
                d1[r["symbol"]].append({"ts_open": r["ts_open"], "c": r["c"]})
        return {"quotes": quotes, "d1": d1}

    async def equity_history(self, account_id, start, end, limit):
        rows = [r for r in self._tab("account_snapshots") if r["account_id"] == account_id
                and (start is None or r["ts"] >= start) and (end is None or r["ts"] <= end)]
        rows.sort(key=lambda r: r["ts"])
        return [{"ts": r["ts"], "balance": r.get("balance"), "equity": r.get("equity"), "margin": r.get("margin")}
                for r in rows[-limit:]]

    async def freshness(self):
        now = datetime.now(timezone.utc)
        spec = [("bars", "bars", "ts_open"), ("quotes", "quotes", "ts"), ("news_items", "news", "published_at"),
                ("calendar_events", "calendar", "ts"), ("expert_signals", "expert_signals", "opened_at"),
                ("expert_positions", "expert_positions", "as_of"), ("account_snapshots", "accounts", "ts"),
                ("alerts", "alerts", "ts")]
        out = []
        for tab, name, col in spec:
            ts = [r[col] for r in self._tab(tab) if r.get(col) and r[col] <= now]  # bỏ mốc tương lai (lịch)
            out.append({"name": name, "last_ts": max(ts) if ts else None,
                        "count_24h": sum(1 for t in ts if now - timedelta(hours=24) <= t <= now)})
        return out

    async def analytics(self, kind, symbol=None, key=None):
        rows = [r for r in self._tab("analytics_snapshots") if r["kind"] == kind
                and (symbol is None or r["payload"].get("symbol") == symbol) and (key is None or r["key"] == key)]
        return sorted(rows, key=lambda r: r["key"])
