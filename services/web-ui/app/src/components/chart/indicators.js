// Động cơ chỉ báo kỹ thuật. Lõi tính toán dùng thư viện OSS `indicatorts` (MIT); chỉ tự viết phần thư viện không có
// (WMA, ADX/DI, Supertrend, Bollinger theo hệ số, VWAP theo ngày, Pivot, Heikin-Ashi) – đều là công thức chuẩn ngắn.
import {
  sma as iSma, ema as iEma, rsi as iRsi, macd as iMacd, atr as iAtr, cci as iCci, obv as iObv, stoch as iStoch,
  psar as iPsar, keltnerChannel as iKelt, donchianChannel as iDonch, williamsR as iWr,
} from "indicatorts";

export const PALETTE = ["#f0b84f", "#5aa9ff", "#c792ea", "#2bd08f", "#ff8a5c", "#4dd0e1", "#ff5c7a", "#aed581"];
const nz = (x) => (Number.isFinite(x) ? x : null);
const cut = (arr, warm) => arr.map((v, i) => (i < warm ? null : nz(v)));
const cutZero = (arr) => arr.map((v) => (Number.isFinite(v) && v !== 0 ? v : null));

/** Cột dữ liệu từ nến [{t,o,h,l,c,v}] */
export function makeCols(bars) {
  const n = bars.length;
  const t = new Array(n), o = new Array(n), h = new Array(n), l = new Array(n), c = new Array(n), v = new Array(n);
  for (let i = 0; i < n; i++) { const b = bars[i]; t[i] = b.t; o[i] = b.o; h[i] = b.h; l[i] = b.l; c[i] = b.c; v[i] = b.v || 0; }
  return { n, t, o, h, l, c, v };
}

// ---------- phần tự viết (công thức chuẩn) ----------
export function wma(x, p) {
  const n = x.length, out = new Array(n).fill(null), den = (p * (p + 1)) / 2;
  for (let i = p - 1; i < n; i++) { let s = 0; for (let k = 0; k < p; k++) s += x[i - p + 1 + k] * (k + 1); out[i] = s / den; }
  return out;
}
function rollStd(x, p) {
  const n = x.length, out = new Array(n).fill(null);
  let s = 0, s2 = 0;
  for (let i = 0; i < n; i++) {
    s += x[i]; s2 += x[i] * x[i];
    if (i >= p) { s -= x[i - p]; s2 -= x[i - p] * x[i - p]; }
    if (i >= p - 1) out[i] = Math.sqrt(Math.max(0, s2 / p - (s / p) * (s / p)));
  }
  return out;
}
export function trueRange(h, l, c) {
  return h.map((hi, i) => (i === 0 ? hi - l[i] : Math.max(hi - l[i], Math.abs(hi - c[i - 1]), Math.abs(l[i] - c[i - 1]))));
}
export function atrWilder(h, l, c, p) {
  const tr = trueRange(h, l, c), n = tr.length, out = new Array(n).fill(null);
  if (n < p) return out;
  let a = 0; for (let i = 0; i < p; i++) a += tr[i];
  a /= p; out[p - 1] = a;
  for (let i = p; i < n; i++) { a = (a * (p - 1) + tr[i]) / p; out[i] = a; }
  return out;
}
export function adx(h, l, c, p) {
  const n = h.length, ADX = new Array(n).fill(null), PDI = new Array(n).fill(null), MDI = new Array(n).fill(null);
  if (n < p * 2) return { adx: ADX, pdi: PDI, mdi: MDI };
  const tr = trueRange(h, l, c);
  const pdm = new Array(n).fill(0), mdm = new Array(n).fill(0);
  for (let i = 1; i < n; i++) {
    const up = h[i] - h[i - 1], dn = l[i - 1] - l[i];
    pdm[i] = up > dn && up > 0 ? up : 0; mdm[i] = dn > up && dn > 0 ? dn : 0;
  }
  let str = 0, sp = 0, sm = 0;
  for (let i = 1; i <= p; i++) { str += tr[i]; sp += pdm[i]; sm += mdm[i]; }
  const dx = new Array(n).fill(null);
  const put = (i) => {
    PDI[i] = str ? (100 * sp) / str : 0; MDI[i] = str ? (100 * sm) / str : 0;
    const s = PDI[i] + MDI[i]; dx[i] = s ? (100 * Math.abs(PDI[i] - MDI[i])) / s : 0;
  };
  put(p);
  for (let i = p + 1; i < n; i++) { str = str - str / p + tr[i]; sp = sp - sp / p + pdm[i]; sm = sm - sm / p + mdm[i]; put(i); }
  let a = 0; for (let i = p; i < p * 2; i++) a += dx[i];
  a /= p; ADX[p * 2 - 1] = a;
  for (let i = p * 2; i < n; i++) { a = (a * (p - 1) + dx[i]) / p; ADX[i] = a; }
  return { adx: ADX, pdi: PDI, mdi: MDI };
}
export function supertrend(h, l, c, p, mult) {
  const n = h.length, up = new Array(n).fill(null), dn = new Array(n).fill(null), dir = new Array(n).fill(0);
  const atr = atrWilder(h, l, c, p);
  let fu = 0, fl = 0, d = 1, started = false;
  for (let i = 0; i < n; i++) {
    if (atr[i] == null) continue;
    const mid = (h[i] + l[i]) / 2, bu = mid + mult * atr[i], bl = mid - mult * atr[i];
    if (!started) { fu = bu; fl = bl; d = c[i] >= mid ? 1 : -1; started = true; }
    else {
      const pc = c[i - 1];
      fu = bu < fu || pc > fu ? bu : fu;
      fl = bl > fl || pc < fl ? bl : fl;
      if (d === 1 && c[i] < fl) d = -1; else if (d === -1 && c[i] > fu) d = 1;
    }
    dir[i] = d;
    if (d === 1) up[i] = fl; else dn[i] = fu;
  }
  return { up, dn, dir };
}
/** VWAP neo theo ngày UTC (reset đầu ngày). Không có ý nghĩa ở khung >= D1. */
export function vwapDaily(cols) {
  const { n, t, h, l, c, v } = cols, out = new Array(n).fill(null);
  let day = -1, pv = 0, vv = 0;
  for (let i = 0; i < n; i++) {
    const d = Math.floor(t[i] / 86400);
    if (d !== day) { day = d; pv = 0; vv = 0; }
    const w = v[i] > 0 ? v[i] : 1;
    pv += ((h[i] + l[i] + c[i]) / 3) * w; vv += w;
    out[i] = pv / vv;
  }
  return out;
}
/** Pivot cổ điển theo kỳ liền trước (ngày UTC với khung < D1, tuần với D1). Đầu mỗi kỳ để null để ngắt nét. */
export function pivotLevels(cols, tfSec) {
  const { n, t, h, l, c } = cols;
  const key = (ts) => (tfSec >= 86400 ? Math.floor((Math.floor(ts / 86400) + 3) / 7) : Math.floor(ts / 86400));
  const names = ["p", "r1", "r2", "r3", "s1", "s2", "s3"];
  const out = Object.fromEntries(names.map((k) => [k, new Array(n).fill(null)]));
  let k0 = null, H = 0, L = 0, C = 0, prev = null;
  for (let i = 0; i < n; i++) {
    const k = key(t[i]);
    if (k !== k0) {
      if (k0 !== null) prev = { H, L, C };
      k0 = k; H = h[i]; L = l[i]; C = c[i];
      continue; // đầu kỳ: ngắt nét
    }
    H = Math.max(H, h[i]); L = Math.min(L, l[i]); C = c[i];
    if (prev) {
      const P = (prev.H + prev.L + prev.C) / 3;
      out.p[i] = P; out.r1[i] = 2 * P - prev.L; out.s1[i] = 2 * P - prev.H;
      out.r2[i] = P + (prev.H - prev.L); out.s2[i] = P - (prev.H - prev.L);
      out.r3[i] = prev.H + 2 * (P - prev.L); out.s3[i] = prev.L - 2 * (prev.H - P);
    }
  }
  return out;
}
export function heikinAshi(bars) {
  const out = new Array(bars.length);
  let po = 0, pc = 0;
  for (let i = 0; i < bars.length; i++) {
    const b = bars[i], c = (b.o + b.h + b.l + b.c) / 4, o = i === 0 ? (b.o + b.c) / 2 : (po + pc) / 2;
    out[i] = { ...b, o, c, h: Math.max(b.h, o, c), l: Math.min(b.l, o, c) };
    po = o; pc = c;
  }
  return out;
}

/** Ichimoku tự tính (cửa sổ cuộn O(n·w)); thư viện indicatorts mất ~5,5s ở 20.000 nến. SSA/SSB dịch tới `medium` nến (mảng dài hơn n). */
export function ichimoku(h, l, c, short, medium, long) {
  const n = h.length;
  const mid = (w) => {
    const out = new Array(n).fill(null);
    for (let i = w - 1; i < n; i++) {
      let hi = -Infinity, lo = Infinity;
      for (let k = i - w + 1; k <= i; k++) { if (h[k] > hi) hi = h[k]; if (l[k] < lo) lo = l[k]; }
      out[i] = (hi + lo) / 2;
    }
    return out;
  };
  const tenkan = mid(short), kijun = mid(medium), sb0 = mid(long);
  const ssa = new Array(n + medium).fill(null), ssb = new Array(n + medium).fill(null), chikou = new Array(n).fill(null);
  for (let i = 0; i < n; i++) {
    if (tenkan[i] != null && kijun[i] != null) ssa[i + medium] = (tenkan[i] + kijun[i]) / 2;
    if (sb0[i] != null) ssb[i + medium] = sb0[i];
    if (i + medium < n) chikou[i] = c[i + medium];
  }
  return { tenkan, kijun, ssa, ssb, chikou };
}

// ---------- danh mục chỉ báo ----------
const P = (k, label, def, min = 1, max = 500, step = 1) => ({ k, label, def, min, max, step });
const bandOut = [{ key: "up", label: "Trên", kind: "line" }, { key: "mid", label: "Giữa", kind: "line", dashed: true }, { key: "lo", label: "Dưới", kind: "line" }];
// outputs: kind line|dots|histsign|histvol ; levels: đường mức cố định trong pane (vd RSI 30/70)
export const IND = {
  sma: { group: "overlay", name: "SMA", desc: "Trung bình động đơn giản", params: [P("period", "Chu kỳ", 20)], outputs: [{ key: "v", label: "SMA", kind: "line" }] },
  ema: { group: "overlay", name: "EMA", desc: "Trung bình động hàm mũ", params: [P("period", "Chu kỳ", 50)], outputs: [{ key: "v", label: "EMA", kind: "line" }] },
  wma: { group: "overlay", name: "WMA", desc: "Trung bình động có trọng số", params: [P("period", "Chu kỳ", 20)], outputs: [{ key: "v", label: "WMA", kind: "line" }] },
  bb: { group: "overlay", name: "Bollinger Bands", desc: "Dải Bollinger", params: [P("period", "Chu kỳ", 20), P("mult", "Độ lệch chuẩn", 2, 0.1, 10, 0.1)], outputs: bandOut },
  vwap: { group: "overlay", name: "VWAP", desc: "VWAP theo ngày (khung < D1)", params: [], outputs: [{ key: "v", label: "VWAP", kind: "line" }] },
  ichimoku: { group: "overlay", name: "Ichimoku", desc: "Ichimoku Kinko Hyo", params: [P("short", "Tenkan", 9), P("medium", "Kijun", 26), P("long", "Senkou B", 52)],
    outputs: [{ key: "tenkan", label: "Tenkan", kind: "line" }, { key: "kijun", label: "Kijun", kind: "line" }, { key: "ssa", label: "Senkou A", kind: "line", fixed: "up" },
      { key: "ssb", label: "Senkou B", kind: "line", fixed: "down" }, { key: "chikou", label: "Chikou", kind: "line", dashed: true }] },
  supertrend: { group: "overlay", name: "Supertrend", desc: "Dải theo ATR", params: [P("period", "ATR", 10), P("mult", "Hệ số", 3, 0.1, 20, 0.1)],
    outputs: [{ key: "up", label: "Tăng", kind: "line", fixed: "up" }, { key: "dn", label: "Giảm", kind: "line", fixed: "down" }] },
  psar: { group: "overlay", name: "Parabolic SAR", desc: "Điểm dừng & đảo chiều", params: [P("step", "Bước", 0.02, 0.001, 1, 0.001), P("max", "Tối đa", 0.2, 0.01, 2, 0.01)], outputs: [{ key: "v", label: "SAR", kind: "dots" }] },
  donchian: { group: "overlay", name: "Donchian", desc: "Kênh Donchian", params: [P("period", "Chu kỳ", 20)], outputs: bandOut },
  keltner: { group: "overlay", name: "Keltner", desc: "Kênh Keltner", params: [P("period", "Chu kỳ", 20), P("mult", "Hệ số ATR", 2, 0.1, 10, 0.1)], outputs: bandOut },
  pivot: { group: "overlay", name: "Pivot Points", desc: "Pivot cổ điển theo kỳ trước", params: [],
    outputs: ["p", "r1", "r2", "r3", "s1", "s2", "s3"].map((k) => ({ key: k, label: k.toUpperCase(), kind: "line", dashed: k !== "p", fixed: k[0] === "r" ? "down" : k[0] === "s" ? "up" : "accent" })) },

  rsi: { group: "pane", name: "RSI", desc: "Sức mạnh tương đối", params: [P("period", "Chu kỳ", 14)], outputs: [{ key: "v", label: "RSI", kind: "line" }], levels: [30, 70] },
  macd: { group: "pane", name: "MACD", desc: "Hội tụ/phân kỳ trung bình động", params: [P("fast", "Nhanh", 12), P("slow", "Chậm", 26), P("signal", "Tín hiệu", 9)],
    outputs: [{ key: "hist", label: "Histogram", kind: "histsign" }, { key: "macd", label: "MACD", kind: "line" }, { key: "sig", label: "Signal", kind: "line" }], levels: [0] },
  stoch: { group: "pane", name: "Stochastic", desc: "Dao động ngẫu nhiên", params: [P("k", "%K", 14), P("smooth", "Làm mượt", 3), P("d", "%D", 3)],
    outputs: [{ key: "k", label: "%K", kind: "line" }, { key: "d", label: "%D", kind: "line" }], levels: [20, 80] },
  atr: { group: "pane", name: "ATR", desc: "Biên độ thực trung bình", params: [P("period", "Chu kỳ", 14)], outputs: [{ key: "v", label: "ATR", kind: "line" }] },
  adx: { group: "pane", name: "ADX", desc: "Độ mạnh xu hướng + DI", params: [P("period", "Chu kỳ", 14)],
    outputs: [{ key: "adx", label: "ADX", kind: "line" }, { key: "pdi", label: "+DI", kind: "line", fixed: "up" }, { key: "mdi", label: "−DI", kind: "line", fixed: "down" }], levels: [20] },
  cci: { group: "pane", name: "CCI", desc: "Commodity Channel Index", params: [P("period", "Chu kỳ", 20)], outputs: [{ key: "v", label: "CCI", kind: "line" }], levels: [-100, 100] },
  wr: { group: "pane", name: "Williams %R", desc: "Williams %R", params: [P("period", "Chu kỳ", 14)], outputs: [{ key: "v", label: "%R", kind: "line" }], levels: [-80, -20] },
  obv: { group: "pane", name: "OBV", desc: "On-Balance Volume", params: [], outputs: [{ key: "v", label: "OBV", kind: "line" }] },
  volume: { group: "pane", name: "Volume", desc: "Khối lượng (pane riêng)", params: [], outputs: [{ key: "v", label: "Vol", kind: "histvol" }] },
};
export const IND_ORDER = Object.keys(IND);

export const defaultParams = (type) => Object.fromEntries(IND[type].params.map((p) => [p.k, p.def]));

/** Màu mặc định cho từng output của 1 instance (seed = thứ tự thêm, để các MA khác chu kỳ có màu khác nhau). */
export function defaultColors(type, seed = 0, theme = {}) {
  const def = IND[type];
  const map = { up: theme.up || "#2bd08f", down: theme.down || "#ff5c7a", accent: theme.accent || "#f0b84f" };
  const out = {};
  def.outputs.forEach((o, i) => { out[o.key] = o.fixed ? map[o.fixed] : PALETTE[(seed + i) % PALETTE.length]; });
  return out;
}

/**
 * Tính 1 chỉ báo. Trả {key: mảng} – độ dài = n (hoặc n+k nếu dịch về tương lai: Ichimoku SSA/SSB).
 * Giá trị chưa đủ dữ liệu = null.
 */
export function compute(type, params, cols, tfSec = 3600) {
  const { n, h, l, c, v } = cols;
  const p = { ...defaultParams(type), ...params };
  const per = Math.max(1, Math.round(p.period || 1));
  switch (type) {
    case "sma": return { v: cut(iSma(c, { period: per }), per - 1) };
    case "ema": return { v: cut(iEma(c, { period: per }), per - 1) };
    case "wma": return { v: wma(c, per) };
    case "bb": {
      const mid = cut(iSma(c, { period: per }), per - 1), sd = rollStd(c, per);
      return { mid, up: mid.map((m, i) => (m == null || sd[i] == null ? null : m + p.mult * sd[i])), lo: mid.map((m, i) => (m == null || sd[i] == null ? null : m - p.mult * sd[i])) };
    }
    case "vwap": return { v: tfSec >= 86400 ? new Array(n).fill(null) : vwapDaily(cols) };
    case "ichimoku": return ichimoku(h, l, c, Math.max(1, Math.round(p.short)), Math.max(1, Math.round(p.medium)), Math.max(1, Math.round(p.long)));
    case "supertrend": { const r = supertrend(h, l, c, per, p.mult); return { up: r.up, dn: r.dn }; }
    case "psar": { const r = iPsar(h, l, c, { step: p.step, max: p.max }); return { v: cut(r.psarResult, 1) }; }
    case "donchian": { const r = iDonch(h, l, { period: per }); return { up: cut(r.upper, per - 1), mid: cut(r.middle, per - 1), lo: cut(r.lower, per - 1) }; }
    case "keltner": {
      const r = iKelt(h, l, c, { period: per }), k = p.mult / 2;
      return {
        mid: cut(r.middle, per - 1),
        up: r.upper.map((u, i) => (i < per - 1 ? null : nz(r.middle[i] + (u - r.middle[i]) * k))),
        lo: r.lower.map((u, i) => (i < per - 1 ? null : nz(r.middle[i] - (r.middle[i] - u) * k))),
      };
    }
    case "pivot": return pivotLevels(cols, tfSec);
    case "rsi": return { v: cut(iRsi(c, { period: per }), per) };
    case "macd": {
      const r = iMacd(c, { fast: p.fast, slow: p.slow, signal: p.signal });
      const macdL = cut(r.macdLine, p.slow - 1), sig = cut(r.signalLine, p.slow + p.signal - 2);
      return { macd: macdL, sig, hist: macdL.map((m, i) => (m == null || sig[i] == null ? null : m - sig[i])) };
    }
    case "stoch": {
      const r = iStoch(h, l, c, { kPeriod: p.k, dPeriod: 1 });
      const ks = p.smooth > 1 ? iSma(r.k, { period: p.smooth }) : r.k;
      const ds = p.d > 1 ? iSma(ks, { period: p.d }) : ks;
      const w1 = p.k - 1 + Math.max(0, p.smooth - 1);
      return { k: cut(ks, w1), d: cut(ds, w1 + Math.max(0, p.d - 1)) };
    }
    case "atr": return { v: cut(iAtr(h, l, c, { period: per }).atrLine, per) };
    case "adx": return adx(h, l, c, per);
    case "cci": return { v: cut(iCci(h, l, c, { period: per }), per - 1) };
    case "wr": return { v: cut(iWr(h, l, c, { period: per }), per - 1) };
    case "obv": return { v: iObv(c, v).map(nz) };
    case "volume": return { v: v.slice() };
    default: return {};
  }
}

// ---------- hàm dùng riêng cho tín hiệu / tóm tắt ----------
export const smaArr = (x, period) => cut(iSma(x, { period }), period - 1);
export const emaArr = (x, period) => cut(iEma(x, { period }), period - 1);
export const rsiArr = (c, period = 14) => cut(iRsi(c, { period }), period);
export const macdArr = (c, fast = 12, slow = 26, signal = 9) => {
  const r = iMacd(c, { fast, slow, signal });
  return { macd: cut(r.macdLine, slow - 1), signal: cut(r.signalLine, slow + signal - 2) };
};
export const cciArr = (h, l, c, period = 20) => cut(iCci(h, l, c, { period }), period - 1);
export const wrArr = (h, l, c, period = 14) => cut(iWr(h, l, c, { period }), period - 1);
