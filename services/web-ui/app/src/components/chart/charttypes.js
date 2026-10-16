// Biến đổi nến -> các loại biểu đồ KHÔNG theo thời gian (Renko, Kagi, Point & Figure, Range, Line Break) tính phía trình duyệt.
// Mọi hàm thuần (không DOM) nên chạy được cả trong Web Worker. Kết quả luôn có thời gian tăng NGHIÊM NGẶT (giây) để nhét vào
// lightweight-charts: mỗi "gạch/cột" lấy thời gian của nến sinh ra nó (+ lệch vài giây khi một nến sinh nhiều gạch).
// Hạn chế (ghi rõ trên giao diện): tính từ OHLC của nến, không phải từng tick; thứ tự High/Low trong nến là giả định.
import { atrWilder } from "./indicators";

export const DERIVED_TYPES = ["renko", "range", "linebreak", "kagi", "pnf"];
export const isDerived = (t) => DERIVED_TYPES.includes(t);

export const CHART_TYPES = [
  { value: "candles", label: "Nến", group: "Cơ bản" },
  { value: "hollow", label: "Nến rỗng", group: "Cơ bản" },
  { value: "ha", label: "Heikin-Ashi", group: "Cơ bản" },
  { value: "bars", label: "Thanh OHLC", group: "Cơ bản" },
  { value: "line", label: "Đường", group: "Cơ bản" },
  { value: "area", label: "Vùng (Area)", group: "Cơ bản" },
  { value: "baseline", label: "Baseline", group: "Cơ bản" },
  { value: "columns", label: "Cột (Columns)", group: "Cơ bản" },
  { value: "renko", label: "Renko", group: "Không theo thời gian" },
  { value: "range", label: "Range bars", group: "Không theo thời gian" },
  { value: "linebreak", label: "Line Break (3)", group: "Không theo thời gian" },
  { value: "kagi", label: "Kagi", group: "Không theo thời gian" },
  { value: "pnf", label: "Point & Figure", group: "Không theo thời gian" },
];

/** Kích thước gạch/hộp mặc định = ATR(14) của dữ liệu, làm tròn tới số đẹp; param > 0 thì dùng param. */
export function autoBox(bars, param, mult = 1) {
  if (param > 0) return param;
  const n = bars.length;
  if (n < 3) return (bars[0]?.h - bars[0]?.l) || 1;
  const h = bars.map((b) => b.h), l = bars.map((b) => b.l), c = bars.map((b) => b.c);
  const a = atrWilder(h, l, c, Math.min(14, n - 1));
  let v = 0;
  for (let i = n - 1; i >= 0; i--) if (a[i] != null) { v = a[i]; break; }
  if (!v) v = (Math.max(...h) - Math.min(...l)) / 50 || 1;
  v *= mult;
  const mag = 10 ** Math.floor(Math.log10(v));
  const f = v / mag;
  return (f < 1.5 ? 1 : f < 3.5 ? 2.5 : f < 7.5 ? 5 : 10) * mag;
}

/** Gán thời gian tăng nghiêm ngặt: nhiều gạch cùng nến được rải đều trong khoảng 1 khung (hoặc +1s khi quá dày). */
function stamp(items, tfSec) {
  // items: [{bt (thời gian nến gốc), ...}] theo thứ tự
  const out = [];
  let i = 0, prev = -Infinity;
  while (i < items.length) {
    let j = i; while (j < items.length && items[j].bt === items[i].bt) j++;
    const cnt = j - i, gap = cnt > 1 ? Math.max(1, Math.floor(tfSec / cnt)) : 0;
    for (let k = 0; k < cnt; k++) {
      let t = items[i].bt + (cnt > 1 ? Math.min(k * gap, tfSec - 1 > 0 ? tfSec - 1 : k) : 0);
      if (t <= prev) t = prev + 1;
      prev = t;
      out.push({ ...items[i + k], t });
    }
    i = j;
  }
  return out;
}

/** Đường đi giả định trong 1 nến: tăng O->L->H->C, giảm O->H->L->C. */
const path = (b) => (b.c >= b.o ? [b.o, b.l, b.h, b.c] : [b.o, b.h, b.l, b.c]);

export function renko(bars, tfSec, size) {
  if (!bars.length) return [];
  const B = size;
  const out = [];
  let top = Math.floor(bars[0].c / B) * B, bot = top; // gạch cuối: [bot, top]; dir 0 = chưa có
  let dir = 0;
  const push = (o, c, bt, v) => out.push({ bt, o, c, h: Math.max(o, c), l: Math.min(o, c), v });
  for (const b of bars) {
    for (const p of path(b)) {
      for (let guard = 0; guard < 500; guard++) {
        if (dir >= 0 && p >= top + B) { push(top, top + B, b.t, b.v); bot = top; top += B; dir = 1; }
        else if (dir <= 0 && p <= bot - B) { push(bot, bot - B, b.t, b.v); top = bot; bot -= B; dir = -1; }
        else if (dir === 1 && p <= bot - B) { push(bot, bot - B, b.t, b.v); top = bot; bot -= B; dir = -1; }
        else if (dir === -1 && p >= top + B) { push(top, top + B, b.t, b.v); bot = top; top += B; dir = 1; }
        else break;
      }
    }
  }
  return stamp(out, tfSec);
}

export function rangeBars(bars, tfSec, R) {
  if (!bars.length) return [];
  const out = [];
  let cur = null, lastV = 0, lastT = bars[0].t;
  for (const b of bars) {
    lastV = b.v; lastT = b.t;
    for (const p of path(b)) {
      if (!cur) cur = { o: p, h: p, l: p };
      const wasUp = p >= cur.h; // điểm này tạo đỉnh mới (đi lên) hay đáy mới
      cur.h = Math.max(cur.h, p); cur.l = Math.min(cur.l, p);
      for (let guard = 0; guard < 500 && cur.h - cur.l >= R * 0.9999; guard++) {
        const up = wasUp && p >= cur.h - 1e-12;
        const c = up ? cur.l + R : cur.h - R;
        out.push({ bt: b.t, o: up ? cur.l : cur.h, c, h: up ? c : cur.h, l: up ? cur.l : c, v: b.v });
        cur = { o: c, h: Math.max(p, c), l: Math.min(p, c) };
        if (cur.h - cur.l < R * 0.9999) break;
      }
    }
  }
  if (cur && cur.h !== cur.l) out.push({ bt: lastT, o: cur.o, c: bars[bars.length - 1].c, h: cur.h, l: cur.l, v: lastV });
  return stamp(out, tfSec);
}

export function lineBreak(bars, tfSec, n = 3) {
  const out = [];
  for (const b of bars) {
    const c = b.c;
    if (!out.length) { out.push({ bt: b.t, o: b.o, c, h: Math.max(b.o, c), l: Math.min(b.o, c), v: b.v }); continue; }
    const last = out[out.length - 1], look = out.slice(-n);
    const hi = Math.max(...look.map((x) => Math.max(x.o, x.c))), lo = Math.min(...look.map((x) => Math.min(x.o, x.c)));
    const lastUp = last.c >= last.o;
    if (c > last.c && (lastUp || c > hi)) out.push({ bt: b.t, o: lastUp ? last.c : last.o, c, h: c, l: lastUp ? last.c : last.o, v: b.v });
    else if (c < last.c && (!lastUp || c < lo)) out.push({ bt: b.t, o: !lastUp ? last.c : last.o, c, h: !lastUp ? last.c : last.o, l: c, v: b.v });
  }
  return stamp(out, tfSec);
}

/** Kagi: điểm = đỉnh/đáy của từng đường; màu theo yang (đang mạnh, xanh) / yin (yếu, đỏ). */
export function kagi(bars, tfSec, rev) {
  if (!bars.length) return [];
  const pts = [];
  let dir = 0, ext = bars[0].c, start = bars[0].c, yang = true;
  let prevHigh = -Infinity, prevLow = Infinity;
  pts.push({ bt: bars[0].t, price: start, yang });
  for (let i = 1; i < bars.length; i++) {
    const p = bars[i].c, bt = bars[i].t;
    if (dir === 0) {
      if (p - start >= rev) { dir = 1; ext = p; } else if (start - p >= rev) { dir = -1; ext = p; } else continue;
      pts[pts.length - 1].price = start;
      pts.push({ bt, price: ext, yang });
      continue;
    }
    if (dir === 1) {
      if (p > ext) { ext = p; pts[pts.length - 1] = { bt, price: ext, yang: ext > prevHigh ? true : yang }; if (ext > prevHigh) yang = true; }
      else if (ext - p >= rev) { prevHigh = ext; dir = -1; ext = p; if (p < prevLow) yang = false; pts.push({ bt, price: ext, yang }); }
    } else if (p < ext) { ext = p; pts[pts.length - 1] = { bt, price: ext, yang: ext < prevLow ? false : yang }; if (ext < prevLow) yang = false; }
    else if (p - ext >= rev) { prevLow = ext; dir = 1; ext = p; if (p > prevHigh) yang = true; pts.push({ bt, price: ext, yang }); }
  }
  return stamp(pts, tfSec).map((q) => ({ t: q.t, bt: q.bt, price: q.price, yang: q.yang }));
}

/** Point & Figure: cột X (tăng) / O (giảm), đảo chiều sau `rev` hộp (mặc định 3). Trả cột {t, lo, hi, dir:1|-1} theo giá hộp. */
export function pnf(bars, tfSec, box, rev = 3) {
  if (!bars.length) return [];
  const cols = [];
  const fl = (p) => Math.floor(p / box + 1e-9) * box; // đáy của hộp chứa p
  let cur = null;
  for (const b of bars) {
    const hiB = fl(b.h), loB = fl(b.l - 1e-9 * box);
    if (!cur) { const x = fl(b.c); cur = { bt: b.t, dir: 0, lo: x, hi: x }; continue; }
    if (cur.dir === 0) {
      if (hiB >= cur.hi + box) { cur.dir = 1; cur.hi = hiB; cur.bt = b.t; cols.push(cur); }
      else if (loB < cur.lo) { cur.dir = -1; cur.hi = cur.hi - box; cur.lo = loB; cur.bt = b.t; if (cur.hi < cur.lo) cur.hi = cur.lo; cols.push(cur); }
      continue;
    }
    if (cur.dir === 1) {
      if (hiB >= cur.hi + box) { cur.hi = hiB; cur.bt = b.t; }
      else if (loB <= cur.hi - rev * box + 1e-9) { cur = { bt: b.t, dir: -1, hi: cur.hi - box, lo: loB }; cols.push(cur); }
    } else if (loB < cur.lo) { cur.lo = loB; cur.bt = b.t; }
    else if (hiB >= cur.lo + rev * box - 1e-9) { cur = { bt: b.t, dir: 1, lo: cur.lo + box, hi: hiB }; cols.push(cur); }
  }
  return stamp(cols.map((c) => ({ ...c })), tfSec).map((c) => ({ t: c.t, lo: c.lo, hi: c.hi, dir: c.dir, box }));
}

/**
 * Chuyển nến thành dữ liệu cho loại biểu đồ không theo thời gian.
 * Trả { bars: [{t,o,h,l,c,v}] } (dùng cho engine vẽ/chỉ báo) và extra (kagi/pnf).
 */
export function deriveBars(type, bars, tfSec, param) {
  if (!bars.length) return { bars: [], extra: null, size: 0 };
  if (type === "renko") { const s = autoBox(bars, param, 1); return { bars: renko(bars, tfSec, s).map(strip), extra: null, size: s }; }
  if (type === "range") { const s = autoBox(bars, param, 0.7); return { bars: rangeBars(bars, tfSec, s).map(strip), extra: null, size: s }; }
  if (type === "linebreak") return { bars: lineBreak(bars, tfSec, 3).map(strip), extra: null, size: 3 };
  if (type === "kagi") {
    const s = autoBox(bars, param, 1.5), pts = kagi(bars, tfSec, s);
    return { bars: pts.map((p) => ({ t: p.t, o: p.price, h: p.price, l: p.price, c: p.price, v: 0 })), extra: pts, size: s };
  }
  if (type === "pnf") {
    const s = autoBox(bars, param, 1), cols = pnf(bars, tfSec, s, 3);
    return { bars: cols.map((c) => ({ t: c.t, o: c.dir > 0 ? c.lo : c.hi + s, h: c.hi + s, l: c.lo, c: c.dir > 0 ? c.hi + s : c.lo, v: 0 })), extra: cols, size: s };
  }
  return { bars, extra: null, size: 0 };
}
const strip = (b) => ({ t: b.t, o: b.o, h: b.h, l: b.l, c: b.c, v: b.v || 0 });

/** Nến Heikin-Ashi giữ nguyên ở indicators.js; đây chỉ gom cho tiện import. */

// ---------- Tạo nến tổng hợp từ 2 mã: spread (A-B) / tỉ lệ (A/B) / phần trăm ----------
/** Ghép theo thời gian (B lấy giá trị gần nhất không muộn hơn). Trả nến tổng hợp cùng trục thời gian với A. */
export function combineBars(a, b, mode) {
  const out = [];
  let j = 0, lb = null;
  for (const x of a) {
    while (j < b.length && b[j].t <= x.t) { lb = b[j]; j++; }
    if (!lb || !lb.c) continue;
    if (mode === "spread") out.push({ t: x.t, o: x.o - lb.o, h: x.h - lb.l, l: x.l - lb.h, c: x.c - lb.c, v: x.v });
    else if (lb.o && lb.h && lb.l) {
      const o = x.o / lb.o, c = x.c / lb.c, hi = x.h / lb.l, lo = x.l / lb.h;
      out.push({ t: x.t, o, h: Math.max(hi, o, c, lo), l: Math.min(lo, o, c, hi), c, v: x.v });
    }
  }
  return out;
}

/** Tương quan Pearson lăn của lợi suất log giữa A và B (cửa sổ w), trả mảng cùng độ dài a (null khi chưa đủ). */
export function rollingCorr(a, b, w = 50) {
  const n = a.length, out = new Array(n).fill(null);
  const rb = []; let j = 0, lb = null;
  for (let i = 0; i < n; i++) {
    while (j < b.length && b[j].t <= a[i].t) { lb = b[j].c; j++; }
    rb.push(lb);
  }
  const ra = new Array(n).fill(null), rbb = new Array(n).fill(null);
  for (let i = 1; i < n; i++) {
    if (a[i].c > 0 && a[i - 1].c > 0) ra[i] = Math.log(a[i].c / a[i - 1].c);
    if (rb[i] > 0 && rb[i - 1] > 0) rbb[i] = Math.log(rb[i] / rb[i - 1]);
  }
  for (let i = w; i < n; i++) {
    let sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0, m = 0;
    for (let k = i - w + 1; k <= i; k++) {
      const x = ra[k], y = rbb[k];
      if (x == null || y == null) continue;
      sx += x; sy += y; sxx += x * x; syy += y * y; sxy += x * y; m++;
    }
    if (m < w * 0.6) continue;
    const cov = sxy / m - (sx / m) * (sy / m), vx = sxx / m - (sx / m) ** 2, vy = syy / m - (sy / m) ** 2;
    if (vx > 0 && vy > 0) out[i] = Math.max(-1, Math.min(1, cov / Math.sqrt(vx * vy)));
  }
  return out;
}
