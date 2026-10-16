"""Kiểm kê phủ dữ liệu: ma trận mã x khung -> {last_bar,last_tick,gaps,status}. Chỉ ĐỌC bars/quotes (role ro), ghi dk.coverage (role rw).

status: OK (dữ liệu đủ tươi) | CLOSED (thị trường đóng theo lịch phiên, không tính lỗi) | SLOW (trễ vừa) | BROKEN (mở cửa mà im lặng/trễ lớn/không có dữ liệu).
Truy vấn rẻ: mỗi khung 1 câu GROUP BY trong cửa sổ ngắn (config.TF_WINDOW); tick: 1 câu 5 phút + tra từng mã còn thiếu (LIMIT 1 theo PK).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from prometheus_client import Gauge

from . import sessions
from .config import TF_SECONDS, TF_WINDOW, get_settings

log = logging.getLogger("data_keeper.inventory")
UTC = timezone.utc
STATUSES = ("OK", "CLOSED", "SLOW", "BROKEN")

G_COV = Gauge("dk_coverage_pct", "Ty le (OK+CLOSED)/tong o ma x khung, theo khung", ["tf"])
G_COV_GRP = Gauge("dk_coverage_group_pct", "Ty le (OK+CLOSED) theo nhom ma (tren moi khung)", ["group"])
G_GAP = Gauge("dk_gap_count", "So nen thieu so voi lich phien (trong cua so kiem ke) theo khung", ["tf"])
G_SILENT = Gauge("dk_symbols_silent_open_market", "So ma mo cua nhung khong co tick/nen moi (BROKEN, M1)")
G_TOTAL = Gauge("dk_symbols_total", "Tong so ma trong kiem ke")
G_STATUS = Gauge("dk_cells_status", "So o (ma x khung) theo trang thai", ["tf", "status"])
G_LASTRUN = Gauge("dk_inventory_last_run_timestamp", "epoch giay lan kiem ke thanh cong cuoi")
G_DUR = Gauge("dk_inventory_duration_seconds", "Thoi gian kiem ke lan cuoi")

THIN_OK_LAG_S = 4 * 3600
G_COV_OPEN = Gauge("dk_coverage_open_pct", "Ty le OK/(OK+SLOW+BROKEN): chi ma dang mo cua co nguon (loai CLOSED/NO_SOURCE), theo khung", ["tf"])
G_THIN = Gauge("dk_thin_symbols", "So ma bao gia thua (khong tinh gap, OK khi im toi da 4 gio)")

SUMMARY: dict = {}   # kết quả tóm tắt lần cuối (cho api/llm đọc): {"at","total","by_tf","silent":[...],"closed_symbols":n}


def classify(*, tf: str, now: datetime, last_bar: datetime | None, last_tick: datetime | None, market_open: bool,
             open_since_s: float | None, cfg=None, thin: bool = False) -> tuple[str, str]:
    """Trả (status, note). Thuần hàm để test."""
    cfg = cfg or get_settings()
    sec = TF_SECONDS[tf]
    tick_fresh = last_tick is not None and (now - last_tick).total_seconds() <= cfg.tick_fresh_s
    # độ trễ so với nến đã ĐÓNG gần nhất kỳ vọng (nến mở tại floor((now-tf)/tf)*tf); âm/0 = kịp
    # nến vừa đóng cần thời gian đến canon (feed gom + ghi): cho ân hạn `ok_lag` sau giờ đóng trước khi coi là thiếu, nếu không
    # kiểm kê chạy ngay sau mốc khung sẽ gắn SLOW hàng loạt (lag luôn là bội của khung).
    # khung >= M5: them 480 s = do tre thiet ke cua rollup (grace 180 s + chu ky kiem ke 300 s) va nen sau restart mt-bridge (rollup.py)
    ok_lag = 120 + min(sec * 0.25, 1800) + (480 if sec >= 300 else 0)
    exp_open = (int(now.timestamp()) - sec - int(ok_lag)) // sec * sec
    lag = None if last_bar is None else exp_open - last_bar.timestamp()
    slow_lag = 600 + 3 * sec
    if not market_open:
        if last_bar is not None and tick_fresh and (now.timestamp() - last_bar.timestamp()) <= sec + ok_lag:
            return "OK", "open_off_schedule"   # lich phien uoc luong sai: co tick + nen tuoi thi thi truong dang mo that
        return ("CLOSED", "no_data" if last_bar is None else "")
    if last_bar is None:
        return ("SLOW" if (thin or (open_since_s is not None and open_since_s < cfg.open_grace_s)) else "BROKEN", "no_bar")
    if lag <= ok_lag:
        return "OK", ""
    if thin and lag <= THIN_OK_LAG_S:   # ma bao gia thua / san it giao dich: nen M1 chi co o phut co giao dich -> im vai gio la binh thuong
        return "OK", "thin_quotes lag=%ds" % int(lag)
    # nến lệch nhưng tick còn tươi (nến đang dựng/chậm canon): SLOW thay vì BROKEN
    in_grace = open_since_s is not None and open_since_s < cfg.open_grace_s
    if lag <= slow_lag or tick_fresh or in_grace:
        return "SLOW", "lag=%ds%s" % (int(lag), " tick_ok" if tick_fresh else "")
    if thin:   # mã báo giá thưa: im lặng là bình thường
        return "SLOW", "thin_quotes lag=%ds" % int(lag)
    return "BROKEN", "lag=%ds" % int(lag)


async def _universe(db, cfg) -> list[str]:
    base: set[str] = set()   # 162 mã MT5 sinh tự động (assets_mt5.yaml); mục viết tay cũ (GER40, DXY...) không thuộc feed MT5
    try:
        import yaml
        from importlib import resources
        d = (yaml.safe_load(resources.files("tscommon").joinpath("assets_mt5.yaml").read_text(encoding="utf-8")) or {}).get("symbols") or {}
        base = {str(it["s"]).upper() for c in ("forex", "metal", "index") for it in d.get(c, [])}
    except Exception as e:  # noqa: BLE001
        log.error("khong doc duoc assets_mt5.yaml: %s", e)
    # crypto (CRYPTO:*): lay tu quotes 1 ngay gan nhat (hypertable, loai chunk theo ts). Truy van DISTINCT tren bars (M1, nhieu ngay) het thoi gian
    # sau khi nap lich su lon (A4); hop them ma da co trong dk.coverage de khong mat ma khi tam im.
    rows = []
    async with db.ro.acquire() as c:
        rows = await c.fetch("SELECT DISTINCT symbol FROM quotes WHERE symbol LIKE 'CRYPTO:%' AND ts > now() - interval '1 day'")
        try:
            rows = list(rows) + list(await c.fetch("SELECT DISTINCT symbol FROM dk.coverage WHERE symbol LIKE 'CRYPTO:%'"))
        except Exception as e:  # noqa: BLE001
            log.warning("khong doc dk.coverage cho universe crypto: %s", e)
    return sorted(base | {r["symbol"] for r in rows})


async def _ticks(db, symbols: list[str], now: datetime) -> dict[str, datetime]:
    out: dict[str, datetime] = {}
    async with db.ro.acquire() as c:
        for r in await c.fetch("SELECT symbol, max(ts) ts FROM quotes WHERE ts > now() - interval '5 minutes' GROUP BY symbol"):
            out[r["symbol"]] = r["ts"]
        for s in symbols:   # mã im: tra tick gần nhất trong 7 ngày (PK symbol,ts -> LIMIT 1)
            if s not in out:
                v = await c.fetchval("SELECT ts FROM quotes WHERE symbol=$1 AND ts > now() - interval '7 days' ORDER BY ts DESC LIMIT 1", s)
                if v:
                    out[s] = v
    return out


async def build_matrix(db) -> dict:
    cfg, t0 = get_settings(), time.monotonic()
    now = datetime.now(UTC).replace(microsecond=0)
    symbols = await _universe(db, cfg)
    ticks = await _ticks(db, symbols, now)
    matrix: dict = {s: {} for s in symbols}
    for tf in cfg.tfs:
        win_start = now - timedelta(seconds=TF_WINDOW[tf])
        async with db.ro.acquire() as c:
            rows = await c.fetch("SELECT symbol, count(DISTINCT ts_open) n, min(ts_open) lo, max(ts_open) hi FROM bars "
                                 "WHERE tf=$1 AND ts_open >= $2 GROUP BY symbol", tf, win_start)
        by = {r["symbol"]: r for r in rows}
        for s in symbols:
            r = by.get(s)
            lb = r["hi"] if r else None
            gaps = expected = present = 0
            if r:
                present = r["n"]
                expected = sessions.expected_slots(s, tf, r["lo"], r["hi"] + timedelta(seconds=TF_SECONDS[tf]))
                gaps = 0 if sessions.is_thin(s) else max(0, expected - present)   # ma thua: phut khong giao dich khong phai lo
            mo = sessions.is_market_open(s, now)
            st, note = classify(tf=tf, now=now, last_bar=lb, last_tick=ticks.get(s), market_open=mo,
                                open_since_s=sessions.open_since(s, now), cfg=cfg, thin=sessions.is_thin(s))
            matrix[s][tf] = {"last_bar": lb, "last_tick": ticks.get(s), "gaps": gaps, "status": st,
                             "expected": expected, "present": present, "market_open": mo, "group": sessions.group_of(s), "note": note}
    _summarize(matrix, cfg, now)
    G_DUR.set(time.monotonic() - t0)
    G_LASTRUN.set(time.time())
    await _store(db, matrix, now)
    return matrix


def _summarize(matrix: dict, cfg, now: datetime) -> dict:
    tot = len(matrix)
    G_TOTAL.set(tot)
    G_THIN.set(sum(1 for s in matrix if sessions.is_thin(s)))
    by_tf, grp_ok, grp_n, silent = {}, {}, {}, []
    for tf in cfg.tfs:
        cnt = dict.fromkeys(STATUSES, 0)
        gaps = 0
        for s, row in matrix.items():
            c = row.get(tf)
            if not c:
                continue
            cnt[c["status"]] += 1
            gaps += c["gaps"]
            g = c["group"]
            grp_n[g] = grp_n.get(g, 0) + 1
            grp_ok[g] = grp_ok.get(g, 0) + (c["status"] in ("OK", "CLOSED"))
        n = max(1, sum(cnt.values()))
        by_tf[tf] = {"counts": cnt, "gaps": gaps, "coverage_pct": round(100.0 * (cnt["OK"] + cnt["CLOSED"]) / n, 2)}
        n_open = cnt["OK"] + cnt["SLOW"] + cnt["BROKEN"]
        by_tf[tf]["coverage_open_pct"] = round(100.0 * cnt["OK"] / n_open, 2) if n_open else 100.0
        G_COV.labels(tf).set(by_tf[tf]["coverage_pct"])
        G_COV_OPEN.labels(tf).set(by_tf[tf]["coverage_open_pct"])
        G_GAP.labels(tf).set(gaps)
        for st in STATUSES:
            G_STATUS.labels(tf, st).set(cnt[st])
    for g, n in grp_n.items():
        G_COV_GRP.labels(g).set(round(100.0 * grp_ok[g] / n, 2))
    ref = "M1" if "M1" in cfg.tfs else cfg.tfs[0]
    for s, row in matrix.items():
        c = row.get(ref)
        if c and c["status"] == "BROKEN":
            silent.append(s)
    G_SILENT.set(len(silent))
    SUMMARY.clear()
    SUMMARY.update({"at": now.isoformat(), "total": tot, "by_tf": by_tf, "silent_open_market": sorted(silent),
                    "closed_symbols": sum(1 for s, r in matrix.items() if r.get(ref) and r[ref]["status"] == "CLOSED")})
    return SUMMARY


async def _store(db, matrix: dict, now: datetime) -> None:
    if not db.rw:
        return
    cols = list(zip(*[(s, tf, c["last_bar"], c["last_tick"], c["gaps"], c["expected"], c["present"], c["status"],
                       c["market_open"], c["group"], c["note"]) for s, row in matrix.items() for tf, c in row.items()]))
    if not cols:
        return
    async with db.rw.acquire() as c:
        await c.execute(
            "INSERT INTO dk.coverage (symbol,tf,last_bar,last_tick,gaps,expected,present,status,market_open,grp,note,updated_at) "
            "SELECT *, now() FROM unnest($1::text[],$2::text[],$3::timestamptz[],$4::timestamptz[],$5::int[],$6::int[],$7::int[],"
            "$8::text[],$9::bool[],$10::text[],$11::text[]) "
            "ON CONFLICT (symbol,tf) DO UPDATE SET last_bar=EXCLUDED.last_bar,last_tick=EXCLUDED.last_tick,gaps=EXCLUDED.gaps,"
            "expected=EXCLUDED.expected,present=EXCLUDED.present,status=EXCLUDED.status,market_open=EXCLUDED.market_open,"
            "grp=EXCLUDED.grp,note=EXCLUDED.note,updated_at=now()", *[list(x) for x in cols])
        await c.execute("DELETE FROM dk.coverage WHERE symbol <> ALL($1::text[])", list(matrix))
