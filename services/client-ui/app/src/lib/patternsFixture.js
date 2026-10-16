// Dữ liệu GIẢ cho trang "Kịch bản" (bật bằng ?mock=1 hoặc ?mockpat=1). Hoàn toàn bịa, theo hợp đồng docs/handoff/SCAN_status.md.
// Ảnh là SVG vẽ tại chỗ (data URL) thay cho PNG máy chủ. Không có tên nguồn.
import { ApiError } from "./api";

let seed = 7;
const rnd = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
const iso = (ms) => new Date(ms).toISOString();
const TFS = { M15: 900e3, H1: 3600e3, H4: 14400e3 };
const BASE = { XAUUSD: [2661.9, 3.2], EURUSD: [1.0861, 0.0011], GBPUSD: [1.2611, 0.0013], "CRYPTO:BTCUSDT": [68420, 420], USDJPY: [150.21, 0.16], XAGUSD: [31.42, 0.08] };

/** Nến giả có dáng "tăng -> giảm mạnh -> hồi -> tích luỹ -> nến giảm kích hoạt". */
function mkBars(symbol, tf, endMs, n = 160, s0 = 1) {
  seed = s0 * 7919 + symbol.length * 31;
  const [p0, atr] = BASE[symbol] || [100, 0.5];
  const step = TFS[tf] || 3600e3;
  const out = [];
  let c = p0 + atr * 6;
  for (let i = 0; i < n; i++) {
    const ph = i / n;
    const drift = ph < 0.25 ? 0.25 : ph < 0.4 ? -1.1 : ph < 0.55 ? 0.55 : ph < 0.95 ? (Math.sin(i / 3) * 0.25) : -1.8;
    const o = c;
    c = o + atr * (drift + (rnd() - 0.5) * 1.1);
    const h = Math.max(o, c) + atr * rnd() * 0.5, l = Math.min(o, c) - atr * rnd() * 0.5;
    out.push({ t: iso(endMs - (n - 1 - i) * step), o, h, l, c });
  }
  return out;
}

/** Vẽ nến thành SVG (nền tối, kiểu ảnh máy chủ) + đường Entry/SL/TP. */
function svg(bars, lv, title, w = 640, h = 300) {
  const lo = Math.min(...bars.map((b) => b.l), lv?.tp_2r ?? Infinity), hi = Math.max(...bars.map((b) => b.h), lv?.sl ?? -Infinity);
  const pad = (hi - lo) * 0.06, y = (p) => 22 + ((hi + pad - p) / (hi - lo + 2 * pad)) * (h - 34);
  const bw = (w - 60) / bars.length;
  let s = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"><rect width="100%" height="100%" fill="#000"/>`;
  bars.forEach((b, i) => {
    const x = 6 + i * bw + bw / 2, up = b.c >= b.o, col = up ? "#26a69a" : "#ef5350";
    s += `<line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${y(b.h).toFixed(1)}" y2="${y(b.l).toFixed(1)}" stroke="${col}"/>`;
    s += `<rect x="${(x - bw * 0.35).toFixed(1)}" y="${y(Math.max(b.o, b.c)).toFixed(1)}" width="${(bw * 0.7).toFixed(1)}" height="${Math.max(1, Math.abs(y(b.o) - y(b.c))).toFixed(1)}" fill="${col}"/>`;
  });
  const ln = (p, c, lb) => (p == null ? "" : `<line x1="0" x2="${w - 56}" y1="${y(p).toFixed(1)}" y2="${y(p).toFixed(1)}" stroke="${c}" stroke-dasharray="5 4"/><text x="${w - 52}" y="${(y(p) + 4).toFixed(1)}" fill="${c}" font-size="11" font-family="monospace">${lb}</text>`);
  if (lv) s += ln(lv.entry, "#f0b84f", "Entry") + ln(lv.sl, "#ff5c7a", "SL") + ln(lv.tp_1r, "#2bd08f", "TP1") + ln(lv.tp_2r, "#2bd08f", "TP2");
  s += `<text x="8" y="15" fill="#fff" font-size="12" font-family="sans-serif">${title}</text></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(s)}`;
}

const STEPS = {
  "KB-1": ["(1) Sóng giảm dẫn hướng mạnh", "(2) Hồi lên <= ~50% sóng (1)", "(3) Giảm nhẹ ≈ sóng (2) (±25%)", "(4) Hồi vượt đỉnh (2) một chút (<= 25% sóng (3))", "(5) Đi ngang tạo 2 đỉnh giảm dần", "(6) Nến nhấn chìm giảm thân dài (đóng nến)"],
  "KB-2": ["(1) Sóng giảm dẫn hướng mạnh", "(2) Hồi ≈50% sóng (1) (25%-75%)", "(3a) Đỉnh thấp dần (>= 3 đỉnh kể cả đỉnh hồi)", "(3b) Đáy cao dần (>= 2 đáy)", "(3c) Nêm thu hẹp (độ rộng hiện tại <= 85% độ rộng ban đầu)", "(4) Nến nhấn chìm giảm thân dài phá cạnh dưới (đóng nến)"],
  "KB-3": ["(1) Sóng giảm dẫn hướng mạnh", "(2) Đi ngang biên độ đều, nến thân vừa", "(3-7) Vai-đầu-vai (vai ≈ nhau, đầu cao hơn, đường cổ phẳng)", "(7) Giá giảm về sát đường cổ", "(8) Cụm 3 nến thân nhỏ nén ở đường cổ (đóng nến)"],
  "KB-4": ["(1) Thị trường đi ngang (hộp)", "(2) Nến thân rất dài phá cạnh dưới hộp", "(3) Chuỗi nến đỏ liên tiếp, sóng giảm dẫn hướng", "(4) Đi ngang mới", "(5) 3 đỉnh giảm dần", "(6) Nến thân nhỏ nén lại (đóng nến)"],
};
const NAMES = { "KB-1": "KB-1: giảm - hồi nhẹ - giảm bằng sóng - vượt đỉnh một chút - 2 đỉnh giảm dần - nhấn chìm", "KB-2": "KB-2: giảm - hồi ~50% - tích luỹ nêm/tam giác thu hẹp - nhấn chìm phá cạnh dưới", "KB-3": "KB-3: giảm - đi ngang biên đều - vai-đầu-vai thuận - cụm 3 nến nén ở đường cổ", "KB-4": "KB-4: đi ngang - nến dài phá đáy - chuỗi nến đỏ - đi ngang mới 3 đỉnh giảm dần - nến nén" };

function mkSetup(i, pattern, symbol, tf, state, agoBars, score) {
  const step = TFS[tf];
  const end = Math.floor(Date.now() / step) * step - agoBars * step;
  const bars = mkBars(symbol, tf, end, 160, i + 1);
  const last = bars[bars.length - 1], atr = BASE[symbol][1];
  const entry = last.c, sl = Math.max(...bars.slice(-30).map((b) => b.h)) + atr * 0.25, r = sl - entry;
  const levels = { entry, sl, tp_1r: entry - r, tp_2r: entry - 2 * r, tp_3r: entry - 3 * r, r, atr };
  const id = `${pattern}:${symbol}:${tf}:${i}`;
  const armedTs = iso(end - 6 * step), trigTs = iso(end);
  const ok = STEPS[pattern].map((label, k) => ({ id: k + 1, label, ok: state === "triggered" || k < STEPS[pattern].length - 1, detail: k === 0 ? "dài 9.4 ATR" : "" }));
  const image = svg(bars.slice(-90), levels, `${symbol.replace(/^[A-Z]+:/, "")}, ${tf}: ${pattern}`);
  const events = [{ id: i * 10 + 1, state: "armed", ts: armedTs, bar_ts: armedTs, score: score - 6, image: svg(bars.slice(-96, -6), null, `${symbol.replace(/^[A-Z]+:/, "")}, ${tf}: ${pattern}`) }];
  if (state === "triggered") events.push({ id: i * 10 + 2, state: "triggered", ts: trigTs, bar_ts: trigTs, score, image });
  return { setup_id: id, pattern, name: NAMES[pattern], symbol, tf, side: "sell", state, score, first_ts: iso(end - 60 * step), last_ts: state === "triggered" ? trigTs : armedTs, bar_ts: trigTs,
    levels, steps: ok, image: state === "triggered" ? image : events[0].image, events, trade: null, _bars: bars };
}

let CACHE = null;
function build() {
  if (CACHE) return CACHE;
  const active = [
    mkSetup(1, "KB-1", "XAUUSD", "M15", "triggered", 2, 82),
    mkSetup(2, "KB-2", "EURUSD", "H1", "armed", 1, 71),
    mkSetup(3, "KB-3", "CRYPTO:BTCUSDT", "H4", "triggered", 1, 77),
    mkSetup(4, "KB-4", "GBPUSD", "M15", "armed", 0, 64),
    mkSetup(5, "KB-2", "XAUUSD", "H1", "triggered", 3, 69),
  ];
  const hist = [];
  const P = ["KB-1", "KB-2", "KB-3", "KB-4"], S = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "XAGUSD"], T = ["M15", "H1", "H4"];
  for (let k = 0; k < 14; k++) hist.push(mkSetup(20 + k, P[k % 4], S[k % 5], T[k % 3], "triggered", 30 + k * 23, 58 + ((k * 7) % 30)));
  const trades = [];
  const outcomes = [2.1, -1, 3, -1, 1.2, -1, 0.4, 2.6, -1, -1, 1.9, -0.3, 3, -1];
  hist.forEach((s, k) => {
    const res = outcomes[k], lv = s.levels;
    const legs = [1, 2, 3].map((m) => {
      const hit = res >= m || (res > 0 && m === 1);
      const status = res <= -1 ? "sl" : hit ? "tp" : res < 0 ? "timeout" : m <= Math.ceil(res) ? "tp" : "sl";
      const r = status === "tp" ? m : status === "sl" ? (res <= -1 ? -1 : 0) : res;
      return { tp: lv.entry - m * lv.r, status, exit: status === "tp" ? lv.entry - m * lv.r : status === "sl" ? lv.sl : lv.entry - res * lv.r, exit_ts: iso(Date.parse(s.last_ts) + (k + 3 + m) * TFS[s.tf]), r };
    });
    const tr = { id: 1000 + k, setup_id: s.setup_id, pattern: s.pattern, symbol: s.symbol, tf: s.tf, side: "sell", opened_at: s.last_ts, entry: lv.entry, sl: lv.sl, r: lv.r, tp: [lv.tp_1r, lv.tp_2r, lv.tp_3r],
      status: "closed", closed_at: legs[2].exit_ts, legs, result_r: res, cost_r: 0.04, mfe_r: Math.max(res, 0) + 0.4, mae_r: -Math.min(0.9, Math.abs(res) * 0.6 + 0.1), bars_held: 6 + k, replay: k > 9, hash: `h${k}`.padEnd(16, "0") };
    s.trade = tr; trades.push(tr);
  });
  active.filter((s) => s.state === "triggered").forEach((s, k) => {
    const lv = s.levels;
    const tr = { id: 2000 + k, setup_id: s.setup_id, pattern: s.pattern, symbol: s.symbol, tf: s.tf, side: "sell", opened_at: s.last_ts, entry: lv.entry, sl: lv.sl, r: lv.r, tp: [lv.tp_1r, lv.tp_2r, lv.tp_3r],
      status: "open", closed_at: null, legs: [1, 2, 3].map((m) => ({ tp: lv.entry - m * lv.r, status: k === 0 && m === 1 ? "tp" : "open", exit: null, exit_ts: null, r: k === 0 && m === 1 ? 1 : null })), result_r: null, cost_r: null, mfe_r: 0.8, mae_r: -0.2, bars_held: 2, replay: false, hash: `o${k}`.padEnd(16, "0") };
    s.trade = tr; trades.push(tr);
  });
  const closed = trades.filter((x) => x.status === "closed").sort((a, b) => Date.parse(a.closed_at) - Date.parse(b.closed_at));
  let cum = 0, peak = 0, dd = 0;
  const equity = closed.map((x) => { cum += x.result_r; peak = Math.max(peak, cum); dd = Math.max(dd, peak - cum); return { t: x.closed_at, cum_r: +cum.toFixed(2) }; });
  const agg = (arr) => { const w = arr.filter((x) => x.result_r > 0), l = arr.filter((x) => x.result_r <= 0); const gp = w.reduce((a, x) => a + x.result_r, 0), gl = -l.reduce((a, x) => a + x.result_r, 0);
    return { n_closed: arr.length, wins: w.length, losses: l.length, winrate: arr.length ? w.length / arr.length : null, avg_r: arr.length ? (gp - gl) / arr.length : null, sum_r: +(gp - gl).toFixed(2), pf: gl ? +(gp / gl).toFixed(2) : null }; };
  const by = (key) => [...new Set(closed.map((x) => x[key]))].sort().map((k) => ({ key: k, ...agg(closed.filter((x) => x[key] === k)) }));
  const stats = { as_of: iso(Date.now()), overall: { ...agg(closed), n_open: trades.length - closed.length, max_dd_r: +dd.toFixed(2) }, by_pattern: by("pattern"), by_tf: by("tf"), by_symbol: by("symbol"), equity,
    ledger: { ok: true, n: trades.length, head: "9f2c4e1a" }, note: "Mô phỏng (paper), mẫu nhỏ." };
  const examples = P.map((p, k) => { const s = hist[k]; return { id: `ex-${p}`, kind: "golden", pattern: p, title: NAMES[p], symbol: s.symbol, tf: s.tf, ts: s.last_ts, note: k === 3 ? "chuỗi nến tổng hợp" : "ví dụ mẫu", image: s.image }; })
    .concat(hist.slice(4, 8).map((s) => ({ id: `live-${s.setup_id}`, kind: "live", pattern: s.pattern, title: NAMES[s.pattern], symbol: s.symbol, tf: s.tf, ts: s.last_ts, note: "", image: s.image })));
  CACHE = { active, hist, trades, stats, examples };
  return CACHE;
}

const pub = (s, withBars) => { const { _bars, ...rest } = s; return withBars ? { ...rest, bars: _bars.map((b) => ({ ts_open: b.t, o: b.o, h: b.h, l: b.l, c: b.c })) } : rest; };
const filt = (arr, p) => arr.filter((s) => (!p.symbol || s.symbol === p.symbol) && (!p.tf || s.tf === p.tf) && (!p.pattern || s.pattern === p.pattern));

export async function handle(path, p = {}) {
  await new Promise((r) => setTimeout(r, 160));
  const d = build();
  if (path === "/patterns/live") {
    const src = p.view === "history" ? d.hist : p.view === "all" ? [...d.active, ...d.hist] : d.active;
    return { items: filt(src, p).slice(0, Number(p.limit) || 100).map((s) => pub(s)), disclaimer: "Chỉ thông tin." };
  }
  if (path === "/patterns/setup") {
    const s = [...d.active, ...d.hist].find((x) => x.setup_id === p.setup_id);
    if (!s) throw new ApiError(404, "Không tìm thấy (hoặc máy chủ chưa hỗ trợ).", "not_found");
    const { bars, ...item } = pub(s, true);
    const piv = bars.filter((_, k) => k % 30 === 10).map((b, k) => ({ t: b.ts_open, p: b.h, label: `(${k + 1})`, kind: "pivot" }));
    const trig = s.state === "triggered" ? [{ t: s.last_ts, p: s.levels.entry, label: "Trigger", kind: "trigger" }] : [];
    return { item: { ...item, bars }, marks: [...piv, ...trig], window: { from: bars[0].ts_open, to: bars[bars.length - 1].ts_open }, disclaimer: "Chỉ thông tin." };
  }
  if (path === "/patterns/trades") {
    const st = p.status && p.status !== "all" ? p.status : null;
    return { items: d.trades.filter((x) => !st || x.status === st).filter((x) => (!p.pattern || x.pattern === p.pattern) && (!p.symbol || x.symbol === p.symbol)).sort((a, b) => Date.parse(b.opened_at) - Date.parse(a.opened_at)) };
  }
  if (path === "/patterns/stats") return d.stats;
  if (path === "/patterns/examples") return { items: d.examples };
  if (path === "/patterns/spec") return { items: Object.keys(STEPS).map((id) => ({ id, name: NAMES[id], side: "sell", summary: "", steps: STEPS[id].map((label, k) => ({ id: k + 1, label })), invalidation: [] })) };
  if (path === "/bars") throw new ApiError(404, "Không tìm thấy (hoặc máy chủ chưa hỗ trợ).", "not_found");
  throw new ApiError(404, "Không tìm thấy (hoặc máy chủ chưa hỗ trợ).", "not_found");
}
