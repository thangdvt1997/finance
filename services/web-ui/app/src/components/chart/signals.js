// Tín hiệu trên biểu đồ + "Tóm tắt kỹ thuật" kiểu TradingView. Tính hoàn toàn phía client từ nến.
// CHỈ LÀ CHỈ BÁO KỸ THUẬT, KHÔNG PHẢI KHUYẾN NGHỊ ĐẦU TƯ.
import { compute, smaArr, emaArr, rsiArr, macdArr, cciArr, wrArr, adx as adxCalc } from "./indicators";

export const SIGNAL_KINDS = [
  { id: "ma", label: "Cắt MA (EMA 20/50)", short: "MA" },
  { id: "rsi", label: "RSI vào/ra quá mua-quá bán", short: "RSI" },
  { id: "macd", label: "MACD cắt Signal", short: "MACD" },
  { id: "bo", label: "Phá vỡ kênh Donchian 20", short: "BO" },
  { id: "div", label: "Phân kỳ RSI (đơn giản)", short: "PK" },
];

const crossUp = (a, b, i) => a[i] != null && b[i] != null && a[i - 1] != null && b[i - 1] != null && a[i - 1] <= b[i - 1] && a[i] > b[i];
const crossDn = (a, b, i) => a[i] != null && b[i] != null && a[i - 1] != null && b[i - 1] != null && a[i - 1] >= b[i - 1] && a[i] < b[i];

/** Điểm xoay (fractal) với k nến mỗi bên. */
function pivots(x, k, high) {
  const out = [];
  for (let i = k; i < x.length - k; i++) {
    let ok = true;
    for (let j = 1; j <= k && ok; j++) ok = high ? x[i] > x[i - j] && x[i] >= x[i + j] : x[i] < x[i - j] && x[i] <= x[i + j];
    if (ok) out.push(i);
  }
  return out;
}

/** → [{i, time, side:"buy"|"sell", kind, text}] (i = chỉ số nến). enabled: Set các kind. */
export function computeSignals(cols, enabled) {
  const { n, t, h, l, c } = cols;
  const out = [];
  if (n < 60) return out;
  const on = (k) => enabled.has(k);
  if (on("ma")) {
    const f = emaArr(c, 20), s = emaArr(c, 50);
    for (let i = 1; i < n; i++) {
      if (crossUp(f, s, i)) out.push({ i, side: "buy", kind: "ma", text: "MA↑" });
      else if (crossDn(f, s, i)) out.push({ i, side: "sell", kind: "ma", text: "MA↓" });
    }
  }
  const r = on("rsi") || on("div") ? rsiArr(c, 14) : null;
  if (on("rsi")) {
    for (let i = 1; i < n; i++) {
      if (r[i] == null || r[i - 1] == null) continue;
      if (r[i - 1] < 30 && r[i] >= 30) out.push({ i, side: "buy", kind: "rsi", text: "RSI 30↑" });
      else if (r[i - 1] > 70 && r[i] <= 70) out.push({ i, side: "sell", kind: "rsi", text: "RSI 70↓" });
    }
  }
  if (on("macd")) {
    const m = macdArr(c);
    for (let i = 1; i < n; i++) {
      if (crossUp(m.macd, m.signal, i)) out.push({ i, side: "buy", kind: "macd", text: "MACD↑" });
      else if (crossDn(m.macd, m.signal, i)) out.push({ i, side: "sell", kind: "macd", text: "MACD↓" });
    }
  }
  if (on("bo")) {
    const per = 20;
    let hi = -Infinity, lo = Infinity;
    for (let i = per; i < n; i++) {
      hi = -Infinity; lo = Infinity;
      for (let k = i - per; k < i; k++) { if (h[k] > hi) hi = h[k]; if (l[k] < lo) lo = l[k]; }
      if (c[i] > hi && c[i - 1] <= hi) out.push({ i, side: "buy", kind: "bo", text: "BO↑" });
      else if (c[i] < lo && c[i - 1] >= lo) out.push({ i, side: "sell", kind: "bo", text: "BO↓" });
    }
  }
  if (on("div")) {
    const K = 3, MAXGAP = 60;
    const lows = pivots(l, K, false), highs = pivots(h, K, true);
    for (let a = 1; a < lows.length; a++) {
      const i0 = lows[a - 1], i1 = lows[a];
      if (i1 - i0 > MAXGAP || r[i0] == null || r[i1] == null) continue;
      if (l[i1] < l[i0] && r[i1] > r[i0] + 1 && r[i1] < 50) out.push({ i: i1 + K, side: "buy", kind: "div", text: "PK↑" });
    }
    for (let a = 1; a < highs.length; a++) {
      const i0 = highs[a - 1], i1 = highs[a];
      if (i1 - i0 > MAXGAP || r[i0] == null || r[i1] == null) continue;
      if (h[i1] > h[i0] && r[i1] < r[i0] - 1 && r[i1] > 50) out.push({ i: i1 + K, side: "sell", kind: "div", text: "PK↓" });
    }
  }
  return out.filter((s) => s.i < n).map((s) => ({ ...s, time: t[s.i] })).sort((a, b) => a.time - b.time);
}

// ---------- Tóm tắt kỹ thuật ----------
const last = (a) => a[a.length - 1];
const prev = (a) => a[a.length - 2];
const vote = (cond) => (cond > 0 ? "buy" : cond < 0 ? "sell" : "neutral");

/** Trả { ma:{items,buy,sell,neutral}, osc:{...}, all:{...}, verdict } ; items: [{name, value, action}] */
export function technicalSummary(cols) {
  const { n, h, l, c } = cols;
  const price = n ? last(c) : null;
  const ma = { items: [] }, osc = { items: [] };
  if (n < 30) return { ma: { ...ma, buy: 0, sell: 0, neutral: 0 }, osc: { ...osc, buy: 0, sell: 0, neutral: 0 }, all: { buy: 0, sell: 0, neutral: 0 }, verdictAll: "neutral", verdictMa: "neutral", verdictOsc: "neutral", ready: false };

  for (const p of [10, 20, 30, 50, 100, 200]) {
    if (n < p + 1) continue;
    const s = last(smaArr(c, p)), e = last(emaArr(c, p));
    if (s != null) ma.items.push({ name: `SMA ${p}`, value: s, action: vote(price - s) });
    if (e != null) ma.items.push({ name: `EMA ${p}`, value: e, action: vote(price - e) });
  }

  const rs = rsiArr(c, 14), rv = last(rs), rp = prev(rs);
  if (rv != null) osc.items.push({ name: "RSI (14)", value: rv, action: rv < 30 && rv > rp ? "buy" : rv > 70 && rv < rp ? "sell" : "neutral" });

  const st = compute("stoch", { k: 14, smooth: 3, d: 3 }, cols), sk = last(st.k), sd = last(st.d);
  if (sk != null && sd != null) osc.items.push({ name: "Stoch %K (14,3,3)", value: sk, action: sk < 20 && sk > sd ? "buy" : sk > 80 && sk < sd ? "sell" : "neutral" });

  const cc = cciArr(h, l, c, 20), cv = last(cc), cpv = prev(cc);
  if (cv != null && cpv != null) osc.items.push({ name: "CCI (20)", value: cv, action: cv < -100 && cv > cpv ? "buy" : cv > 100 && cv < cpv ? "sell" : "neutral" });

  const ad = adxCalc(h, l, c, 14), av = last(ad.adx), pd = last(ad.pdi), md = last(ad.mdi);
  if (av != null) osc.items.push({ name: "ADX (14)", value: av, action: av > 20 && pd > md ? "buy" : av > 20 && pd < md ? "sell" : "neutral" });

  const hl2 = h.map((x, i) => (x + l[i]) / 2), a5 = smaArr(hl2, 5), a34 = smaArr(hl2, 34);
  const aoNow = a5[n - 1] != null && a34[n - 1] != null ? a5[n - 1] - a34[n - 1] : null;
  const aoPrev = a5[n - 2] != null && a34[n - 2] != null ? a5[n - 2] - a34[n - 2] : null;
  if (aoNow != null && aoPrev != null) osc.items.push({ name: "Awesome Osc.", value: aoNow, action: aoNow > 0 && aoNow > aoPrev ? "buy" : aoNow < 0 && aoNow < aoPrev ? "sell" : "neutral" });

  if (n > 12) {
    const m0 = c[n - 1] - c[n - 11], m1 = c[n - 2] - c[n - 12];
    osc.items.push({ name: "Momentum (10)", value: m0, action: vote(m0 - m1) });
  }

  const mc = macdArr(c), mv = last(mc.macd), sv = last(mc.signal);
  if (mv != null && sv != null) osc.items.push({ name: "MACD (12,26,9)", value: mv, action: vote(mv - sv) });

  const wr = wrArr(h, l, c, 14), wv = last(wr), wp = prev(wr);
  if (wv != null && wp != null) osc.items.push({ name: "Williams %R (14)", value: wv, action: wv < -80 && wv > wp ? "buy" : wv > -20 && wv < wp ? "sell" : "neutral" });

  const tally = (items) => {
    const t = { buy: 0, sell: 0, neutral: 0 };
    for (const it of items) t[it.action]++;
    return t;
  };
  Object.assign(ma, tally(ma.items));
  Object.assign(osc, tally(osc.items));
  const all = { buy: ma.buy + osc.buy, sell: ma.sell + osc.sell, neutral: ma.neutral + osc.neutral };
  return { ma, osc, all, verdictAll: verdict(all), verdictMa: verdict(ma), verdictOsc: verdict(osc), ready: true };
}

/** Ngưỡng như TradingView: (mua − bán)/tổng, ±0.1 và ±0.5. */
export function verdict(t) {
  const tot = t.buy + t.sell + t.neutral;
  if (!tot) return "neutral";
  const s = (t.buy - t.sell) / tot;
  return s >= 0.5 ? "strong_buy" : s >= 0.1 ? "buy" : s <= -0.5 ? "strong_sell" : s <= -0.1 ? "sell" : "neutral";
}
/** -1..1 cho kim đồng hồ */
export function verdictScore(t) {
  const tot = t.buy + t.sell + t.neutral;
  return tot ? (t.buy - t.sell) / tot : 0;
}
export const VERDICT_LABEL = { strong_buy: "Mua mạnh", buy: "Mua", neutral: "Trung lập", sell: "Bán", strong_sell: "Bán mạnh" };
export const ACTION_LABEL = { buy: "Mua", sell: "Bán", neutral: "Trung lập" };
