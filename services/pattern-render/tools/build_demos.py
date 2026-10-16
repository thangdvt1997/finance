"""Dung lai 3 anh mau (XAUUSD M15) tu nen thuc + annotation nhap tay theo toa do diem anh goc.
Chay TREN VPS:  python tools/build_demos.py CANDLES.json OUT_DIR [--basis auto|none]
CANDLES.json = [{t(epoch UTC), o,h,l,c}] M15. Gio anh mau = gio san broker (UTC+3).
--basis auto: tru hang so de dinh cao nhat cua cua so khop dinh cao cua anh mau (dung khi nguon la hop dong tuong lai, lech gia so voi spot);
              che do none dung khi nguon la spot.
Toa do annotation: (x, y) diem anh goc 1920x899 -> chi so nen i=(x-2)/bw (bw=8 diem/nen; anh 3 la 4), gia theo 2 moc truc gia cua anh.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pattern_render import render_signal  # noqa: E402

TZ = 3  # gio san = UTC+3
N = 231


def make_px(y0, p0, y1, p1, bw=8.0):
    k = (p1 - p0) / (y1 - y0)

    def px(x, y):
        return {"i": round((x - 2) / bw, 2), "p": round(p0 + (y - y0) * k, 2)}
    return px


def L(px, a, b, label=None, arrow=False, at=None):
    d = {"from": px(*a), "to": px(*b), "arrow": arrow, "label": label}
    if at:
        d["label_at"] = px(*at)
    return d


def spec1():
    px = make_px(9, 4219.82, 843, 4136.36)
    return dict(
        name="demo1_tam_giac_30sep", bar0=(2026, 9, 30, 3, 0), top_y=14, px=px, scenario="Kich ban SELL: tam giac sau song giam - 4 buoc",
        ann={
            "legs": [L(px, (403, 14), (753, 810), "(1)", True, (578, 361)), L(px, (762, 815), (920, 288), "(2)", True, (826, 489))],
            "lines": [
                {"kind": "boundary", "from": px(874, 264), "to": px(1546, 395)},
                {"kind": "boundary", "from": px(930, 782), "to": px(1546, 417)},
            ],
            "labels": [{"at": px(1050, 387), "text": "(3)"}],
            "arrows": [{"from": px(1531, 322), "to": px(1484, 420), "label": "(4)"}],
        })


def spec2():
    px = make_px(10, 4229.30, 843, 4107.10)
    return dict(
        name="demo2_song_5-6_oct", bar0=(2026, 10, 1, 21, 45), top_y=14, px=px, scenario="Kich ban SELL: song hoi + dinh thap dan - 6 buoc",
        ann={
            "legs": [
                L(px, (539, 14), (648, 713), "(1)", True, (643, 331)),
                L(px, (658, 715), (937, 462), "(2)", True, (794, 535)),
                L(px, (947, 462), (1010, 720), "(3)", True, (987, 545)),
                L(px, (1025, 720), (1153, 418), "(4)", True, (1106, 587)),
                L(px, (1122, 405), (1274, 427), "(5)", True, (1202, 395)),
            ],
            "zones": [{"from": px(975, 534), "to": px(999, 557)}],
            "arrows": [{"from": px(1371, 392), "to": px(1252, 455), "label": "(6)"}],
        })


def spec3():
    px = make_px(10, 4377.12, 843, 4147.80, 4.0)
    return dict(
        name="demo3_hop_21-28sep", bar0=(2026, 9, 21, 11, 45), n=462, top_y=14, px=px, scenario="Kich ban SELL: hop di ngang + pha day - 8 buoc",
        ann={
            "legs": [
                L(px, (543, 33), (877, 381), "(1)", True, (679, 221)),
                L(px, (1356, 312), (1417, 447), "(3)", False, (1379, 393)),
                L(px, (1417, 447), (1512, 238), "(4)", False, (1451, 316)),
                L(px, (1512, 238), (1559, 456), "(5)", False, (1519, 376)),
                L(px, (1559, 456), (1641, 302), "(6)", False, (1599, 422)),
                L(px, (1641, 302), (1684, 445), "(7)", False, (1646, 377)),
            ],
            "lines": [
                {"kind": "boundary", "from": px(898, 229), "to": px(1646, 233)},
                {"kind": "boundary", "from": px(910, 488), "to": px(1654, 493)},
            ],
            "labels": [{"at": px(1115, 255), "text": "(2)"}],
            "zones": [{"from": px(1686, 413), "to": px(1718, 448)}],
            "arrows": [{"from": px(1750, 338), "to": px(1707, 407), "label": "(8)"}],
        })


def spec4_levels(base):
    """Bien the demo3 + entry/SL/TP goi y (kiem tra duong net dut)."""
    px = base["px"]
    a = json.loads(json.dumps(base["ann"]))
    a["levels"] = [{"kind": "entry", "price": px(0, 449)["p"], "label": "Entry"}, {"kind": "sl", "price": px(0, 229)["p"], "label": "SL"},
                   {"kind": "tp", "price": px(0, 645)["p"], "label": "TP (do cao hop)"}]
    return dict(base, name="demo4_levels_entry_sl_tp", ann=a, scenario="Kich ban SELL (co Entry/SL/TP goi y)")


def window(rows, bar0, n=N):
    import calendar
    t0 = calendar.timegm((*bar0, 0, 0, 0)) - TZ * 3600
    ws = [r for r in rows if r["t"] >= t0][:n]
    return ws


def main():
    src, out = sys.argv[1], Path(sys.argv[2])
    basis_mode = sys.argv[sys.argv.index("--basis") + 1] if "--basis" in sys.argv else "auto"
    rows = json.load(open(src))
    out.mkdir(parents=True, exist_ok=True)
    s3 = spec3()
    for sp in (spec1(), spec2(), s3, spec4_levels(s3)):
        ws = window(rows, sp["bar0"], sp.get("n", N))
        basis = 0.0
        if basis_mode == "auto":
            basis = max(r["h"] for r in ws) - sp["px"](0, sp["top_y"])["p"]
        cs = [{k: (v - basis if k in "ohlc" else v) for k, v in r.items()} for r in ws]
        ann = dict(sp["ann"], title={"symbol": "XAUUSD", "tf": "M15", "scenario": sp["scenario"]}, tz_offset_h=TZ,
                   style={"right_pad_bars": 0.5, "left_pad_bars": 0.25, "digits": 2, "xtick_bars": 32 if len(ws) > 300 else 16}, watermark="Pattern Lab - mo phong")
        png = render_signal(cs, ann, out / (sp["name"] + ".png"), size=(1920, 900), max_kb=150)
        print(sp["name"], len(ws), "nen", f"basis={basis:.2f}", len(png) // 1024, "KB")


if __name__ == "__main__":
    main()
