"""Biểu đồ SVG inline tự sinh (không matplotlib). Màu theo skill dataviz: 1 hue chủ đạo (xanh #2a78d6), phân cực xanh/cam;
in trắng-đen vẫn đọc được: dương = nền đặc, âm = nền gạch chéo, luôn kèm nhãn số và ký hiệu ▲/▼."""
from __future__ import annotations

from itertools import count
from xml.sax.saxutils import escape

from markupsafe import Markup

POS, NEG, INK, GRID = "#2a78d6", "#eb6834", "#1f2328", "#d0d4d9"
_ids = count(1)


def _f(v: float) -> str:
    return f"{v:.1f}"


def sparkline(values: list[float], w: int = 96, h: int = 26, title: str = "") -> Markup:
    vals = [float(v) for v in values if v is not None]
    if len(vals) < 2:
        return Markup(f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="không đủ dữ liệu"></svg>')
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    pts = [(1 + i / (len(vals) - 1) * (w - 2), h - 2 - (v - lo) / span * (h - 4)) for i, v in enumerate(vals)]
    col = POS if vals[-1] >= vals[0] else NEG
    line = " ".join(f"{_f(x)},{_f(y)}" for x, y in pts)
    area = f"{line} {_f(w - 1)},{h} 1,{h}"
    lx, ly = pts[-1]
    t = f"<title>{escape(title)}</title>" if title else ""
    return Markup(
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title or "xu hướng")}">{t}'
        f'<polygon points="{area}" fill="{col}" opacity=".13"/>'
        f'<polyline points="{line}" fill="none" stroke="{col}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{_f(lx)}" cy="{_f(ly)}" r="2.2" fill="{col}" stroke="#fff" stroke-width="1"/></svg>')


def hbar(rows: list[tuple[str, float | None]], w: int = 520, unit: str = "%", digits: int = 2, label_w: int = 118,
         row_h: int = 17) -> Markup:
    """Cột ngang phân cực quanh 0: rows = [(nhãn, giá trị)]. Giá trị None bỏ qua."""
    rows = [(l, float(v)) for l, v in rows if v is not None]
    if not rows:
        return Markup("")
    uid = next(_ids)
    m = max(abs(v) for _, v in rows) or 1.0
    right = 64
    plot = w - label_w - right
    zero = label_w + plot / 2
    half = plot / 2
    h = row_h * len(rows) + 6
    out = [f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="biểu đồ cột">'
           f'<defs><pattern id="hatch{uid}" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
           f'<rect width="5" height="5" fill="#fff"/><rect width="2.2" height="5" fill="{NEG}"/></pattern></defs>',
           f'<line x1="{_f(zero)}" y1="2" x2="{_f(zero)}" y2="{h - 2}" stroke="{GRID}" stroke-width="1"/>']
    for i, (lab, v) in enumerate(rows):
        y = 3 + i * row_h
        bw = abs(v) / m * (half - 4)
        x = zero if v >= 0 else zero - bw
        fill = POS if v >= 0 else f"url(#hatch{uid})"
        stroke = "" if v >= 0 else f' stroke="{NEG}" stroke-width=".8"'
        txt = f"{'▲' if v > 0 else '▼' if v < 0 else '■'} {v:+.{digits}f}{unit}"
        tx = zero + bw + 4 if v >= 0 else zero + 4
        anchor = "start"
        out.append(f'<text x="{label_w - 6}" y="{y + row_h * .68:.1f}" text-anchor="end" font-size="9.5" fill="{INK}">{escape(lab)}</text>')
        out.append(f'<rect x="{_f(x)}" y="{y + 2}" width="{max(bw, .8):.1f}" height="{row_h - 6}" rx="2" fill="{fill}"{stroke}/>')
        out.append(f'<text x="{_f(tx)}" y="{y + row_h * .68:.1f}" text-anchor="{anchor}" font-size="9" fill="{INK}">{txt}</text>')
    out.append("</svg>")
    return Markup("".join(out))


def meter(used: float | None, warn: float = 0.6, crit: float = 0.85, w: int = 150, h: int = 12, label: str = "") -> Markup:
    """Thanh tiêu thụ ngân sách/giới hạn: used = tỷ lệ 0..1 (có thể >1). Ký hiệu ✓ / ! / ✕ kèm nhãn % (không chỉ dựa vào màu)."""
    if used is None:
        return Markup('<span class="muted">—</span>')
    u = max(0.0, float(used))
    fill = min(u, 1.0) * (w - 2)
    state, glyph = ("ok", "✓") if u < warn else (("warn", "!") if u < crit else ("crit", "✕"))
    col = {"ok": POS, "warn": "#eda100", "crit": NEG}[state]
    uid = next(_ids)
    pat = f'<pattern id="mh{uid}" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="4" height="4" fill="{col}"/><rect width="1.6" height="4" fill="#fff" opacity=".55"/></pattern>'
    fl = f"url(#mh{uid})" if state == "crit" else col
    return Markup(
        f'<span class="meter {state}"><svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(label)} {u * 100:.0f}%">'
        f'<defs>{pat}</defs><rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="3" fill="#eef0f2" stroke="{GRID}"/>'
        f'<rect x="1" y="1" width="{fill:.1f}" height="{h - 2}" rx="3" fill="{fl}"/></svg>'
        f'<b>{glyph} {u * 100:.0f}%</b></span>')


def stacked_share(parts: list[tuple[str, int]], w: int = 260, h: int = 12) -> Markup:
    """Thanh tỷ trọng (tin tích cực/trung lập/tiêu cực): có nhãn số bên dưới nên không phụ thuộc màu."""
    tot = sum(n for _, n in parts) or 1
    cols = [POS, "#9aa3ad", NEG]
    x, out = 0.0, [f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="tỷ trọng">']
    for i, (lab, n) in enumerate(parts):
        bw = n / tot * w
        if bw > 0:
            out.append(f'<rect x="{x:.1f}" y="0" width="{max(bw - 2, 0):.1f}" height="{h}" rx="2" fill="{cols[i % 3]}"><title>{escape(lab)}: {n}</title></rect>')
        x += bw
    out.append("</svg>")
    return Markup("".join(out))
