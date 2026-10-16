"""Vẽ ảnh nến PNG thuần numpy + zlib (worker không có matplotlib; không mạng). Phong cách MT4: nền đen, nến xanh/đỏ, vạch SL/vào lệnh,
dải sáng ở nến tín hiệu. Không chứa tên nguồn dữ liệu / chữ nào (không cần font): thông tin đi kèm ở JSON, UI hiển thị."""
from __future__ import annotations

import struct
import zlib

import numpy as np

BG = (0, 0, 0)
UP = (0, 220, 0)
DN = (235, 40, 40)
SIG = (60, 60, 20)
LV = {"entry": (255, 212, 0), "sl": (255, 90, 90)}


def _png(rgb: np.ndarray) -> bytes:
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))

    def chunk(t: bytes, d: bytes) -> bytes:
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def render(o, h, l, c, sig_pos: int, levels: dict | None = None, size=(900, 450)) -> bytes:
    """o,h,l,c: mảng cùng độ dài (cửa sổ nến); sig_pos: chỉ số nến tín hiệu trong cửa sổ; levels: {'entry':giá,'sl':giá}."""
    w, hh = size
    o, h, l, c = (np.asarray(x, dtype=float) for x in (o, h, l, c))
    n = len(c)
    img = np.zeros((hh, w, 3), dtype=np.uint8)
    lo_p, hi_p = float(np.nanmin(l)), float(np.nanmax(h))
    for v in (levels or {}).values():
        if v is not None and np.isfinite(v):
            lo_p, hi_p = min(lo_p, float(v)), max(hi_p, float(v))
    pad = (hi_p - lo_p) * 0.06 or 1e-6
    lo_p, hi_p = lo_p - pad, hi_p + pad
    left, right, top, bot = 6, 6, 10, 10
    pw, ph = w - left - right, hh - top - bot
    step = pw / max(n, 1)
    bw = max(1, int(step * 0.62))

    def y(p: float) -> int:
        return int(round(top + (hi_p - p) / (hi_p - lo_p) * (ph - 1)))
    if 0 <= sig_pos < n:
        x0 = int(left + sig_pos * step)
        img[:, x0:int(x0 + step) + 1] = SIG
    for i in range(n):
        xc = int(left + (i + 0.5) * step)
        col = UP if c[i] >= o[i] else DN
        yh, yl = y(h[i]), y(l[i])
        img[min(yh, yl):max(yh, yl) + 1, xc] = col
        yo, yc = y(o[i]), y(c[i])
        ya, yb = min(yo, yc), max(yo, yc)
        img[ya:yb + 1, max(0, xc - bw // 2):xc - bw // 2 + bw] = col
    for k, v in (levels or {}).items():
        if v is None or not np.isfinite(v) or k not in LV:
            continue
        yy = min(max(y(float(v)), 0), hh - 1)
        img[yy, left:w - right:3] = LV[k]
    return _png(img)
