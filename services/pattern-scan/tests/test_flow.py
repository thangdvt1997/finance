from datetime import timedelta

from fastapi.testclient import TestClient

from pattern_scan import annot
from pattern_scan.app import create_app
from pattern_scan.config import DEFAULTS, Settings
from pattern_scan.notify import Ntfy
from pattern_scan.store import MemoryStore
from pattern_scan.worker import Scanner

from .conftest import DT, make_bars, payload, ts


class Sender:
    def __init__(self, code=200):
        self.calls, self.code = [], code

    def __call__(self, url, body, headers):
        self.calls.append((url, body, headers))
        return self.code


def mk(now_i: int, rows=None, code=200):
    rows = rows or make_bars()
    st = MemoryStore({("XAUUSD", "M15"): rows})
    snd = Sender(code)
    sc = Scanner(DEFAULTS | {}, st, Ntfy("http://ntfy", "t", sender=snd), clock=lambda: ts(now_i) + DT + timedelta(seconds=5))
    return sc, st, snd, rows


def test_png_signature_and_annotations(bars):
    p = payload("armed", 200, bars)
    cs = [{"t": r["ts_open"].timestamp(), "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"]} for r in bars[:201]]
    ann, marks = annot.build(p, cs)
    labels = [m["label"] for m in marks]
    assert "(1)" in labels and "(2)" in labels
    assert ann["legs"] and ann["title"]["symbol"] == "XAUUSD"
    assert "GMT+7" in ann["title"]["time"]


async def test_triggered_flow_image_trade_notify_close():
    sc, st, snd, rows = mk(200)
    out = await sc.handle(payload("triggered", 200, rows))
    assert out["live"] and out["image"] and out["trade_id"] == 1 and out["notified"]
    url, body, headers = snd.calls[0]
    assert body[:8] == b"\x89PNG\r\n\x1a\n" and "filename=" in url and headers["Content-Type"] == "image/png"
    assert "ĐÃ KÍCH HOẠT" in __import__("urllib.parse").parse.unquote_plus(url)
    # trùng sự kiện -> bỏ qua, không lệnh mới
    assert (await sc.handle(payload("triggered", 200, rows)))["skip"] == "trùng"
    # nến sau kích hoạt: chưa đóng -> không xử lý
    assert (await sc.monitor())["closed_now"] == 0 and st.tr[0]["bars_held"] == 0
    # cho thời gian trôi tới nến 230, ép SL bằng nến cao bất thường
    rows[205] = dict(rows[205], h=rows[200]["c"] + 50)
    sc.clock = lambda: ts(240)
    res = await sc.monitor()
    assert res["closed_now"] == 1 and st.tr[0]["status"] == "closed" and st.tr[0]["result_r"] < -1
    assert [r["kind"] for r in st.led] == ["open", "close"]
    assert "Paper đóng" in __import__("urllib.parse").parse.unquote_plus(snd.calls[-1][0])


async def test_replay_not_notified_and_flagged():
    sc, st, snd, rows = mk(260)
    out = await sc.handle(payload("triggered", 200, rows))          # nhận trễ 60 nến -> replay
    assert not out["live"] and "notified" not in out and not snd.calls
    assert st.tr[0]["replay"] is True


async def test_forming_not_notified_and_attachment_fallback():
    sc, st, snd, rows = mk(150)
    await sc.handle(payload("forming", 150, rows, setup_id="KB-2:20261001T0000:20261001T0100"))
    assert not snd.calls
    sc2, _, snd2, _ = mk(200, code=400)
    out = await sc2.handle(payload("armed", 200, rows))
    assert len(snd2.calls) == 2 and snd2.calls[1][1] in (None, b"") and out["notified"] is False


async def test_api_master_vs_client():
    sc, st, snd, rows = mk(200)
    await sc.handle(payload("forming", 190, rows, setup_id="KB-4:20261002T1000"))
    await sc.handle(payload("armed", 195, rows))
    await sc.handle(payload("triggered", 200, rows))
    await sc.handle(payload("armed", 196, rows, setup_id="KB-1:20261002T1000:20261002T1200", pattern="KB-1"))
    await sc.handle(payload("invalid", 199, rows, setup_id="KB-1:20261002T1000:20261002T1200", pattern="KB-1", reason="đóng trên đỉnh"))
    app = create_app(Settings(examples_dir="/nonexistent"), scanner=sc)
    with TestClient(app) as c:
        m = c.get("/scan/setups", params={"view": "all"}).json()["items"]
        assert {i["state"] for i in m} == {"forming", "triggered", "invalid"}
        trig = next(i for i in m if i["state"] == "triggered")
        assert trig["trade"]["status"] == "open" and trig["image"].startswith("/v1/patterns/media/")
        cl = c.get("/scan/setups", params={"view": "all", "audience": "client"}).json()["items"]
        assert [i["state"] for i in cl] == ["triggered"]               # forming + setup đã huỷ bị ẩn
        assert all(e["state"] in ("armed", "triggered") for e in cl[0]["events"]) and "reason" not in cl[0]
        act = c.get("/scan/setups", params={"view": "active"}).json()["items"]
        assert act[0]["state"] == "triggered"                          # lệnh còn mở = vẫn "hiện tại"
        forming_ev = next(e for e in st.ev if e["state"] == "forming")["id"]
        assert c.get(f"/scan/media/{forming_ev}.png").status_code == 200
        assert c.get(f"/scan/media/{forming_ev}.png", params={"audience": "client"}).status_code == 404
        d = c.get("/scan/setup", params={"setup_id": trig["setup_id"], "symbol": "XAUUSD", "tf": "M15"}).json()
        assert any(mk_["kind"] == "trigger" for mk_ in d["marks"]) and d["window"]["from"] < d["window"]["to"]
        assert c.get("/scan/setup", params={"setup_id": "KB-1:20261002T1000:20261002T1200", "symbol": "XAUUSD", "tf": "M15",
                                            "audience": "client"}).status_code == 404
        s = c.get("/scan/stats").json()
        assert s["ledger"]["ok"] and s["overall"]["n_open"] == 1
        assert c.get("/scan/trades").json()["items"][0]["hash"]
        ex = c.get("/scan/examples").json()["items"]
        assert ex and ex[0]["kind"] == "live"
        assert c.get("/scan/examples/..%2Fetc.png").status_code == 404


async def test_backfill_from_table():
    rows = make_bars()
    st = MemoryStore({("XAUUSD", "M15"): rows}, signals=[payload("armed", 195, rows)])
    sc = Scanner(DEFAULTS, st, Ntfy("http://ntfy", "t", sender=Sender()), clock=lambda: ts(300))
    assert await sc.backfill() == 1 and await sc.backfill() == 0


async def test_repair_missing_image_and_trade():
    sc, st, snd, rows = mk(200)
    p = payload("triggered", 200, rows)
    eid = await st.insert_event(p, True)            # mô phỏng: lưu sự kiện xong thì lỗi (chưa ảnh, chưa lệnh)
    assert eid and not st.img and not st.tr
    assert await sc.repair() == 2
    assert eid in st.img and st.tr[0]["replay"] is False
    assert await sc.repair() == 0


def test_backtest_artifacts_api(tmp_path):
    import gzip, json
    (tmp_path / "charts").mkdir(); (tmp_path / "examples").mkdir(); (tmp_path / "ledger").mkdir()
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 16
    (tmp_path / "charts" / "a1_equity.png").write_bytes(png)
    (tmp_path / "examples" / "KB-1_thang_D1_XAUUSD_M5.png").write_bytes(png)
    (tmp_path / "examples" / "x.txt").write_text("no")
    (tmp_path / "ledger" / "ledger_summary.csv").write_text("split,n\ndev,1\n")
    (tmp_path / "ledger" / "ledger_test.csv.gz").write_bytes(gzip.compress(b"id\n1\n"))
    (tmp_path / "ledger" / "secret.csv").write_text("x")
    (tmp_path / "summary.json").write_text(json.dumps({"verdict": "Không có edge sau chi phí", "rows": []}), encoding="utf-8")
    with TestClient(create_app(Settings(backtest_dir=str(tmp_path), examples_dir="/nonexistent"), scanner=mk(10)[0])) as c:
        d = c.get("/scan/backtest/summary").json()
        assert d["verdict"].startswith("Không có edge") and [x["name"] for x in d["charts"]] == ["a1_equity.png"]
        assert [x["name"] for x in d["examples"]] == ["KB-1_thang_D1_XAUUSD_M5.png"]
        assert {x["name"] for x in d["downloads"]} == {"ledger_summary.csv", "ledger_test.csv.gz"}
        assert c.get("/scan/backtest/charts/a1_equity.png").content.startswith(b"\x89PNG")
        r = c.get("/scan/backtest/download/ledger_summary.csv")
        assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
        assert c.get("/scan/backtest/download/secret.csv").status_code == 404      # ngoài danh sách trắng
        assert c.get("/scan/backtest/download/..%2Fsummary.json").status_code == 404
        assert c.get("/scan/backtest/charts/..%2Fsummary.json").status_code == 404
        assert c.get("/scan/backtest/charts/x.txt").status_code == 404
        assert c.get("/scan/backtest/other/a1_equity.png").status_code == 404
    with TestClient(create_app(Settings(backtest_dir="/nonexistent", examples_dir="/nonexistent"), scanner=mk(10)[0])) as c:
        assert c.get("/scan/backtest/summary").status_code == 200


async def test_patterns_enabled_rong_tat_quet():
    sc, st, snd, rows = mk(200)
    sc.cfg = {**sc.cfg, "patterns_enabled": []}
    assert (await sc.handle(payload("triggered", 200, rows)))["skip"] == "kịch bản tắt"
    assert not snd.calls and not st.tr
    sc.cfg = {**sc.cfg, "patterns_enabled": [payload("triggered", 200, rows)["pattern"]]}
    assert "skip" not in await sc.handle(payload("triggered", 200, rows))
