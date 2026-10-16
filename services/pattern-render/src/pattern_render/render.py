"""render_signal(candles, annotations) -> PNG. Phong cach MT4: nen den, nen xanh/do, nhan trang (1)(2).., truc gia ben phai.

Headless (backend Agg), thuan Python (matplotlib + numpy + pillow). Truc X theo CHI SO nen (khong khoang trong cuoi tuan, giong MT4).
Khong chua ten nguon du lieu: chi ma, khung, kich ban, thoi diem + watermark tuy chinh.
"""
from __future__ import annotations

import io
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from matplotlib.ticker import FixedLocator  # noqa: E402

from .schema import norm_candles, validate_annotations  # noqa: E402

BG = "#000000"
FG = "#ffffff"
UP = "#00ff00"
DN = "#ff0000"
LEVEL_STYLE = {"entry": ("#ffd400", "Entry"), "sl": ("#ff5050", "SL"), "tp": ("#40e0ff", "TP")}


class _X:
    """Doi thoi gian/chi so -> toa do X (chi so nen, co the le)."""

    def __init__(self, candles: list[dict]):
        self.t = np.array([c["t"] for c in candles])
        self.n = len(candles)
        self.step = float(np.median(np.diff(self.t))) if self.n > 1 else 900.0

    def __call__(self, pt: dict) -> float:
        if "i" in pt:
            return float(pt["i"])
        t = pt["t"]
        if t <= self.t[0]:
            return (t - self.t[0]) / self.step
        if t >= self.t[-1]:
            return self.n - 1 + (t - self.t[-1]) / self.step
        return float(np.interp(t, self.t, np.arange(self.n)))


def _digits(price: float, forced: int | None) -> int:
    if forced is not None:
        return int(forced)
    return 2 if price >= 50 else 5


def _fmt_t(epoch: float, tz_h: float) -> str:
    d = datetime.fromtimestamp(epoch, tz=timezone.utc) + timedelta(hours=tz_h)
    return f"{d.day} {d.strftime('%b %H:%M')}"


def _build_figure(candles: list[dict], ann: dict, size: tuple[int, int], dpi: int):
    n = len(candles)
    xs = _X(candles)
    st = ann["style"]
    w, h = size
    fig = plt.figure(figsize=(w / dpi, h / dpi), dpi=dpi, facecolor=BG)
    ax = fig.add_axes([0.001, 0.05, 0.9625, 0.94], facecolor=BG)
    ax.yaxis.tick_right()

    hi = max(c["h"] for c in candles)
    lo = min(c["l"] for c in candles)
    extra = [lv["price"] for lv in ann["levels"]]
    for g in ann["legs"] + ann["lines"] + ann["zones"] + ann["arrows"]:
        extra += [g["a"]["p"], g["b"]["p"]]
    hi, lo = max([hi] + extra), min([lo] + extra)
    pad = (hi - lo) * 0.03 or 1.0
    ax.set_ylim(lo - pad, hi + pad)
    right_pad = float(st["right_pad_bars"]) if "right_pad_bars" in st else max(4.0, n * 0.04)
    ax.set_xlim(-float(st.get("left_pad_bars", 1.0)), n - 1 + right_pad)

    idx = np.arange(n)
    o = np.array([c["o"] for c in candles])
    hh = np.array([c["h"] for c in candles])
    ll = np.array([c["l"] for c in candles])
    cc = np.array([c["c"] for c in candles])
    up = cc >= o
    bw = float(st.get("body_width", 0.62))
    lw_px = max(0.6, min(1.2, 90.0 / max(n, 1)))
    for mask, col in ((up, UP), (~up, DN)):
        if not mask.any():
            continue
        ax.vlines(idx[mask], ll[mask], hh[mask], colors=col, linewidth=lw_px * 0.9, zorder=2)
        body_lo = np.minimum(o, cc)[mask]
        body_hi = np.maximum(o, cc)[mask]
        body_hi = np.maximum(body_hi, body_lo + (hi - lo) * 0.0004)  # doji van thay duoc
        ax.bar(idx[mask], body_hi - body_lo, bottom=body_lo, width=bw, color=col, linewidth=0, zorder=3)

    line_kw = dict(color=FG, linewidth=float(st.get("line_width", 1.0)), solid_capstyle="butt", zorder=5)
    arrow_kw = dict(arrowstyle="-|>", color=FG, lw=1.0, mutation_scale=11, shrinkA=0, shrinkB=0)
    fs = float(st.get("label_size", 12))

    def label(txt, x, y):
        if txt:
            ax.text(x, y, txt, color=FG, fontsize=fs, ha="center", va="center", zorder=8)

    for g in ann["lines"]:
        x1, x2 = xs(g["a"]), xs(g["b"])
        y1, y2 = g["a"]["p"], g["b"]["p"]
        if g["arrow"]:
            ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=arrow_kw, zorder=6)
        else:
            ax.plot([x1, x2], [y1, y2], **line_kw)
        if g["label"]:
            la = g["label_at"]
            label(g["label"], xs(la) if la else (x1 + x2) / 2, la["p"] if la else (y1 + y2) / 2 + pad * 0.6)

    for g in ann["legs"]:
        x1, x2 = xs(g["a"]), xs(g["b"])
        y1, y2 = g["a"]["p"], g["b"]["p"]
        if g["arrow"]:
            ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=arrow_kw, zorder=6)
        else:
            ax.plot([x1, x2], [y1, y2], **line_kw)
        if g["label"]:
            la = g.get("label_at")
            if la:
                label(g["label"], xs(la), la["p"])
            else:  # lech sang ben ngoai doan: xuong -> phai, len -> trai
                off = max(2.0, n * 0.012) * (1 if y2 < y1 else -1)
                label(g["label"], (x1 + x2) / 2 + off, (y1 + y2) / 2)

    for g in ann["zones"]:
        x1, x2 = sorted((xs(g["a"]), xs(g["b"])))
        y1, y2 = sorted((g["a"]["p"], g["b"]["p"]))
        ax.add_patch(Rectangle((x1, y1), x2 - x1, y2 - y1, fill=g["fill"], facecolor=(1, 1, 1, 0.10),
                               edgecolor=FG, linewidth=1.0, zorder=6))
        if g["label"]:
            label(g["label"], (x1 + x2) / 2, y2 + pad * 0.5)

    for g in ann["arrows"]:  # mui ten kich hoat: duoi -> dau nhon
        x1, x2 = xs(g["a"]), xs(g["b"])
        ax.annotate("", xy=(x2, g["b"]["p"]), xytext=(x1, g["a"]["p"]), arrowprops=arrow_kw, zorder=7)
        if g["label"]:
            dy = pad * 0.9 * (1 if g["a"]["p"] >= g["b"]["p"] else -1)
            label(g["label"], x1, g["a"]["p"] + dy)

    for g in ann["labels"]:
        label(g["text"], xs(g["at"]), g["at"]["p"])

    dg = _digits(cc[-1], st.get("digits"))
    xr = ax.get_xlim()[1]
    for lv in ann["levels"]:
        col, nm = LEVEL_STYLE[lv["kind"]]
        ax.axhline(lv["price"], color=col, linestyle=(0, (5, 4)), linewidth=1.0, zorder=4, alpha=0.95)
        txt = f"{lv['label'] or nm}  {lv['price']:.{dg}f}"
        ax.text(xr - 0.4, lv["price"], txt, color=col, fontsize=9, ha="right", va="bottom", zorder=8)

    if st.get("last_price_line", True):
        ax.axhline(cc[-1], color="#8a8a8a", linewidth=0.8, zorder=1)
        ax.text(1.003, cc[-1], f"{cc[-1]:.{dg}f}", transform=ax.get_yaxis_transform(), color="#000000", fontsize=8,
                ha="left", va="center", bbox=dict(boxstyle="square,pad=0.15", fc="#c8c8c8", ec="none"),
                zorder=9, clip_on=False)

    ymin, ymax = ax.get_ylim()
    raw = (ymax - ymin) / 26.0
    mag = 10 ** np.floor(np.log10(raw))
    stepp = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=raw)
    ticks = np.arange(np.ceil(ymin / stepp) * stepp, ymax, stepp)
    ax.yaxis.set_major_locator(FixedLocator(ticks))
    ax.set_yticklabels([f"{v:.{dg}f}" for v in ticks], color=FG, fontsize=8)
    ax.tick_params(axis="y", colors=FG, length=3, pad=3)
    k = int(st["xtick_bars"]) if "xtick_bars" in st else max(1, int(round(n / 15.0)))
    pos = list(range(0, n, k))
    ax.set_xticks(pos)
    ax.set_xticklabels([_fmt_t(candles[p]["t"], ann["tz_offset_h"]) for p in pos], color=FG, fontsize=8)
    if pos and pos[0] == 0:
        ax.get_xticklabels()[0].set_ha("left")
    ax.tick_params(axis="x", colors=FG, length=3, pad=3)
    for s in ax.spines.values():
        s.set_color(FG)
        s.set_linewidth(0.8)

    ti = ann["title"]
    head = ", ".join(x for x in (ti.get("symbol"), ti.get("tf")) if x)
    rest = "  ".join(str(ti[key]) for key in ("scenario", "time") if ti.get(key))
    if head or rest:
        ax.text(0.004, 0.992, (head + ":  " if head and rest else head) + rest, transform=ax.transAxes, color=FG,
                fontsize=float(st.get("title_size", 9.5)), ha="left", va="top", zorder=10)
    if ann["watermark"]:
        ax.text(0.012, 0.015, ann["watermark"], transform=ax.transAxes, color="#ffffff", alpha=0.28, fontsize=11,
                ha="left", va="bottom", zorder=1)
    return fig


def render_png_bytes(candles: list, annotations: dict | None = None, *, size: tuple[int, int] = (1600, 800),
                     dpi: int = 100, max_kb: int | None = None) -> bytes:
    """candles: [{t,o,h,l,c}] hoac [[t,o,h,l,c]]; t = ISO8601/epoch giay (UTC). annotations: xem docs/PATTERNS_SELL.md#render.
    max_kb: neu dat, luong tu mau (PIL) cho PNG <= nguong (cham nhe do net)."""
    cs = norm_candles(candles)
    ann = validate_annotations(annotations)
    fig = _build_figure(cs, ann, size, dpi)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG, dpi=dpi)
    plt.close(fig)
    data = buf.getvalue()
    if max_kb and len(data) > max_kb * 1024:
        from PIL import Image
        im = Image.open(io.BytesIO(data)).convert("RGB")
        for colors in (128, 96, 64, 48, 32, 24, 16):
            q = im.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
            b = io.BytesIO()
            q.save(b, format="PNG", optimize=True)
            data = b.getvalue()
            if len(data) <= max_kb * 1024:
                break
    return data


def render_signal(candles: list, annotations: dict | None = None, out_path: str | os.PathLike | None = None, **kw) -> bytes:
    """Ve anh kich ban. Tra ve bytes PNG; neu co out_path thi ghi them ra file. Tham so: xem render_png_bytes."""
    data = render_png_bytes(candles, annotations, **kw)
    if out_path:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return data
