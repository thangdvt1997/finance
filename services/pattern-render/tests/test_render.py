import io
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np
import pytest
from PIL import Image

from pattern_render import SchemaError, render_signal, validate_annotations
from pattern_render.cli import _handler, main

T0 = 1_790_000_000 - (1_790_000_000 % 900)


def make_candles(n=120, seed=3):
    rng = np.random.default_rng(seed)
    p = 4200.0
    out = []
    for k in range(n):
        o = p
        c = o + rng.normal(0, 2.0)
        h = max(o, c) + abs(rng.normal(0, 1.2))
        l = min(o, c) - abs(rng.normal(0, 1.2))
        out.append({"t": T0 + 900 * k, "o": o, "h": h, "l": l, "c": c})
        p = c
    return out


def full_ann(cs):
    t = lambda i: cs[i]["t"]
    return {
        "title": {"symbol": "XAUUSD", "tf": "M15", "scenario": "KB1 test", "time": "2026-10-01 10:00"},
        "legs": [
            {"from": {"t": t(5), "p": cs[5]["h"]}, "to": {"t": t(40), "p": cs[40]["l"]}, "arrow": True, "label": "(1)"},
            {"from": {"i": 40, "p": cs[40]["l"]}, "to": {"i": 70, "p": cs[70]["h"]}, "label": "(2)"},
        ],
        "lines": [{"kind": "boundary", "from": {"i": 40, "p": cs[40]["h"]}, "to": {"i": 100, "p": cs[100]["h"]}}],
        "zones": [{"from": {"i": 95, "p": cs[95]["h"]}, "to": {"i": 99, "p": cs[95]["l"]}}],
        "arrows": [{"from": {"i": 105, "p": cs[100]["h"] + 8}, "to": {"i": 100, "p": cs[100]["h"]}, "label": "(3)"}],
        "levels": [{"kind": "entry", "price": cs[100]["c"]}, {"kind": "sl", "price": cs[100]["c"] + 9},
                   {"kind": "tp", "price": cs[100]["c"] - 18}],
    }


def to_img(png):
    return Image.open(io.BytesIO(png)).convert("RGB")


def test_png_basic_style():
    cs = make_candles()
    png = render_signal(cs, full_ann(cs))
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    im = to_img(png)
    assert im.size == (1600, 800)
    a = np.asarray(im).reshape(-1, 3)
    black = (a.sum(axis=1) < 30).mean()
    assert black > 0.80  # nen den
    assert ((a[:, 1] > 200) & (a[:, 0] < 60) & (a[:, 2] < 60)).sum() > 500  # nen xanh
    assert ((a[:, 0] > 200) & (a[:, 1] < 60) & (a[:, 2] < 60)).sum() > 500  # nen do
    assert ((a > 235).all(axis=1)).sum() > 500  # net/nhan trang


def test_annotations_change_picture():
    cs = make_candles()
    plain = np.asarray(to_img(render_signal(cs, {"watermark": ""}))).astype(int)
    full = np.asarray(to_img(render_signal(cs, {**full_ann(cs), "watermark": ""}))).astype(int)
    assert np.abs(plain - full).sum() > 100_000


def test_levels_dashed_colors_present():
    cs = make_candles()
    a = np.asarray(to_img(render_signal(cs, full_ann(cs)))).reshape(-1, 3)
    assert ((a[:, 0] > 200) & (a[:, 1] > 150) & (a[:, 1] < 235) & (a[:, 2] < 90)).sum() > 40  # entry vang


def test_time_or_index_points_equivalent():
    cs = make_candles()
    a1 = {"legs": [{"from": {"t": cs[10]["t"], "p": cs[10]["h"]}, "to": {"t": cs[30]["t"], "p": cs[30]["l"]}}], "watermark": ""}
    a2 = {"legs": [{"from": {"i": 10, "p": cs[10]["h"]}, "to": {"i": 30, "p": cs[30]["l"]}}], "watermark": ""}
    assert render_signal(cs, a1) == render_signal(cs, a2)


def test_deterministic():
    cs = make_candles()
    assert render_signal(cs, full_ann(cs)) == render_signal(cs, full_ann(cs))


def test_max_kb_enforced():
    cs = make_candles(400)
    png = render_signal(cs, full_ann(cs), max_kb=60)
    assert len(png) <= 60 * 1024
    to_img(png)


def test_no_source_names_in_output():
    cs = make_candles()
    png = render_signal(cs, full_ann(cs))
    low = png.lower()
    for bad in (b"dukascopy", b"yahoo", b"mt4", b"mt5", b"metaquotes"):
        assert bad not in low


def test_out_path(tmp_path):
    cs = make_candles(60)
    p = tmp_path / "x" / "o.png"
    render_signal(cs, {}, out_path=p)
    assert p.read_bytes()[:4] == b"\x89PNG"


@pytest.mark.parametrize("bad", [
    {"levels": [{"kind": "foo", "price": 1}]},
    {"lines": [{"kind": "zzz", "from": {"i": 1, "p": 1}, "to": {"i": 2, "p": 1}}]},
    {"legs": [{"from": {"p": 1}, "to": {"i": 2, "p": 1}}]},
])
def test_schema_errors(bad):
    with pytest.raises(SchemaError):
        validate_annotations(bad)


def test_candles_validation():
    with pytest.raises(SchemaError):
        render_signal([], {})
    with pytest.raises(SchemaError):
        render_signal([{"t": 1, "o": 5, "h": 4, "l": 3, "c": 4}], {})
    with pytest.raises(SchemaError):
        render_signal([{"t": 2, "o": 1, "h": 2, "l": 1, "c": 1}, {"t": 1, "o": 1, "h": 2, "l": 1, "c": 1}], {})


def test_array_candles_and_iso_time():
    rows = [["2026-10-01T00:00:00Z", 10, 12, 9, 11], ["2026-10-01T00:15:00+00:00", 11, 13, 10, 12],
            ["2026-10-01T00:30:00", 12, 12.5, 11, 11.5]]
    assert render_signal(rows, {"legs": [{"from": {"t": "2026-10-01T00:00:00Z", "p": 12}, "to": {"i": 2, "p": 11}}]})[:4] == b"\x89PNG"


def test_http_api():
    cs = make_candles(50)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _handler())
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        body = json.dumps({"candles": cs, "annotations": full_ann(make_candles(120))}).encode()
        r = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/render", data=body), timeout=30)
        assert r.headers["Content-Type"] == "image/png" and r.read()[:4] == b"\x89PNG"
        assert urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz").status == 200
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/render", data=b'{"candles": []}'))
        assert e.value.code == 400
    finally:
        srv.shutdown()


def test_cli(tmp_path):
    cs = make_candles(40)
    (tmp_path / "c.json").write_text(json.dumps(cs))
    (tmp_path / "a.json").write_text(json.dumps({"title": {"symbol": "X"}}))
    assert main(["render", "--candles", str(tmp_path / "c.json"), "--ann", str(tmp_path / "a.json"), "--out", str(tmp_path / "o.png")]) == 0
    assert (tmp_path / "o.png").stat().st_size > 1000
