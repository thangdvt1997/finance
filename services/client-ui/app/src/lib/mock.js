// Máy chủ GIẢ chạy trong trình duyệt (bật bằng cờ ?mock=1). Dùng để xem/thử giao diện khi auth/gateway chưa sẵn sàng.
// Dữ liệu hoàn toàn bịa; không có tên nguồn. KHÔNG dùng cho sản xuất thật (giao diện hiện nhãn "Dữ liệu mẫu").
import { ApiError } from "./api";
import { handleToday } from "./mock_today";
import { handleNotif } from "./mock_notif";
import { handlePrefs } from "./mock_prefs";

let seed = 20261012;
const rnd = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
const gauss = () => { let u = 0, v = 0; while (!u) u = rnd(); while (!v) v = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
const NOW = () => Date.now();
const iso = (ms) => new Date(ms).toISOString();
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const SKEY = "tc-mock-sess";

// ---------- người dùng/tài khoản mẫu ----------
const USERS = {
  "mt5:12345678": { pw: "demo-cong-1", name: "Nguyễn Minh Anh", accounts: ["mt5:12345678", "mt4:7654321"], must: false },
  "mt4:7654321": { pw: "doi-mat-khau-1", name: "Nguyễn Minh Anh", accounts: ["mt5:12345678", "mt4:7654321"], must: true },
  "mt4:55555555": { pw: null, code: "PAIR-2468", name: "Trần Quốc Bảo", accounts: ["mt4:55555555"], must: false },
};
const ACC = {
  "mt5:12345678": { platform: "mt5", login: "12345678", server: "BrokerX-Live01", label: "Tài khoản chính", status: "active", balance: 12480.55, ageS: 9, hedging: true },
  "mt4:7654321": { platform: "mt4", login: "7654321", server: "BrokerX-Demo", label: "Thử nghiệm", status: "active", balance: 5000, ageS: 7200 },
  "mt4:55555555": { platform: "mt4", login: "55555555", server: "BrokerY-Live", label: "", status: "active", balance: 2000, ageS: 20 },
};
const load = () => { try { return JSON.parse(sessionStorage.getItem(SKEY) || "null"); } catch { return null; } };
const save = (s) => { try { s ? sessionStorage.setItem(SKEY, JSON.stringify(s)) : sessionStorage.removeItem(SKEY); } catch { /* bỏ qua */ } };
let fails = 0, lockedUntil = 0;
const MSG = { 401: "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.", 403: "Bạn không có quyền xem mục này.", 404: "Không tìm thấy (hoặc máy chủ chưa hỗ trợ)." };
const err = (status, detail, extra) => { throw new ApiError(status, MSG[status] || detail, detail, extra); };

function me() {
  const s = load();
  if (!s) err(401, "unauthenticated");
  const u = USERS[s.key];
  return { user_id: `u-${s.key}`, role: "client", display_name: u.name, must_change_password: !!s.must,
    login: s.key, accounts: u.accounts, totp_enabled: false };
}

async function authCall(method, path, body) {
  await wait(250);
  if (path === "/me") return me();
  if (path === "/login" && method === "POST") {
    if (Date.now() < lockedUntil) err(423, "locked", Math.ceil((lockedUntil - Date.now()) / 1000));
    const key = `${body.platform}:${body.login}`;
    const u = USERS[key];
    if (!u || !u.pw || u.pw !== body.secret) {
      if (++fails >= 5) { fails = 0; lockedUntil = Date.now() + 45_000; err(423, "locked", 45); }
      err(401, "invalid");
    }
    fails = 0; save({ key, must: u.must, created: Date.now() });
    return { ok: true, must_change_password: u.must };
  }
  if (path === "/pair" && method === "POST") {
    const key = `${body.platform}:${body.login}`;
    const u = USERS[key];
    if (!u || u.code !== body.pairing_code) err(401, "invalid_pairing");
    if (!body.new_password || body.new_password.length < 10) err(422, "Mật khẩu mới tối thiểu 10 ký tự.");
    u.pw = body.new_password; u.code = null; save({ key, must: false, created: Date.now() });
    return { ok: true };
  }
  if (path === "/change-password" && method === "POST") {
    const s = load(); if (!s) err(401, "unauthenticated");
    const u = USERS[s.key];
    if (u.pw !== body.current_password) err(401, "wrong_password");
    u.pw = body.new_password; save({ ...s, must: false });
    return { ok: true };
  }
  if (path === "/logout") { save(null); return { ok: true }; }
  if (path === "/sessions" && method === "GET") {
    const s = load(); if (!s) err(401, "unauthenticated");
    return { items: [
      { id: "s1", current: true, created_at: iso(s.created), last_seen_at: iso(NOW()), ip: "203.0.113.24", user_agent: navigator.userAgent },
      { id: "s2", current: false, created_at: iso(NOW() - 3 * 86400e3), last_seen_at: iso(NOW() - 5 * 3600e3), ip: "198.51.100.7", user_agent: "Safari trên iPhone" },
    ] };
  }
  if (/^\/sessions\/.+\/revoke$/.test(path) && method === "POST") return { ok: true };
  if (path === "/logout-all") { save(null); return { ok: true }; }
  err(404, "not_found");
}

// ---------- dữ liệu tài khoản ----------
const POS = {
  "mt5:12345678": [
    { position_id: "9001", symbol: "EURUSD", side: "buy", volume: 0.5, price_open: 1.0832, price_current: 1.0861, sl: 1.079, tp: 1.092, profit: 145.0, swap: -1.2, time_open: iso(NOW() - 26 * 3600e3) },
    { position_id: "9002", symbol: "XAUUSD", side: "sell", volume: 0.1, price_open: 2652.4, price_current: 2661.9, sl: 0, tp: 2610, profit: -95.0, swap: -0.8, time_open: iso(NOW() - 5 * 3600e3) },
    { position_id: "9003", symbol: "USDJPY", side: "buy", volume: 0.2, price_open: 150.5, price_current: 150.214, sl: 149.0, tp: 0, profit: -38.1, swap: 0.4, time_open: iso(NOW() - 2 * 3600e3) },
    { position_id: "9004", symbol: "GBPUSD", side: "sell", volume: 0.3, price_open: 1.2645, price_current: 1.2611, sl: 1.272, tp: 1.25, profit: 102.0, swap: -0.5, time_open: iso(NOW() - 9 * 3600e3) },
  ],
  "mt4:7654321": [{ position_id: "5001", symbol: "EURUSD", side: "buy", volume: 0.1, price_open: 1.0850, price_current: 1.0861, sl: 1.08, tp: 0, profit: 11.0, swap: 0, time_open: iso(NOW() - 40 * 3600e3) }],
  "mt4:55555555": [],
};
const ORDERS = {
  "mt5:12345678": [
    { order_id: "7001", symbol: "EURUSD", kind: "buy_limit", volume: 0.3, price: 1.0790, sl: 1.075, tp: 1.088, time_setup: iso(NOW() - 4 * 3600e3) },
    { order_id: "7002", symbol: "XAUUSD", kind: "sell_stop", volume: 0.05, price: 2630, sl: 2650, tp: 2580, time_setup: iso(NOW() - 3600e3) },
  ],
};
function snap(id) {
  const a = ACC[id], pos = POS[id] || [];
  const floating = pos.reduce((s, p) => s + p.profit, 0);
  const equity = +(a.balance + floating).toFixed(2);
  const margin = pos.length ? +(pos.reduce((s, p) => s + p.volume * 1000, 0)).toFixed(2) : 0;
  const o = { account_id: id, platform: a.platform, ts: iso(NOW() - a.ageS * 1000), balance: a.balance, equity, margin, positions: pos };
  if (ORDERS[id]) o.orders = ORDERS[id];
  return o;
}
function equityHistory(id, from) {
  const a = ACC[id];
  const t0 = from ? Date.parse(from) : NOW() - 7 * 86400e3;
  const end = NOW() - a.ageS * 1000;
  const step = Math.max(300e3, Math.round((end - t0) / 400 / 60e3) * 60e3);
  const out = []; let eq = a.balance - 220; const r = (id.length * 7919) % 97;
  seed = 777 + r;
  for (let t = t0; t <= end; t += step) { eq += gauss() * 9 + 0.35; out.push({ ts: iso(t), balance: +(a.balance - 60 + Math.floor((t - t0) / 86400e3) * 14).toFixed(2), equity: +eq.toFixed(2), margin: 500 }); }
  if (out.length) out[out.length - 1].equity = snap(id).equity;
  return out;
}
function riskFor(id) {
  const s = snap(id), pos = s.positions;
  const level = s.margin ? (s.equity / s.margin) * 100 : null;
  const uw = []; let peak = 0, cum = 0; seed = 4242;
  for (let i = 0; i < 90; i++) { cum += gauss() * 0.4 + 0.05; peak = Math.max(peak, cum); uw.push({ t: Math.floor((NOW() - (90 - i) * 6 * 3600e3) / 1000), dd: +(cum - peak).toFixed(2) }); }
  return {
    generated_at: iso(NOW()), disclaimer: "Số liệu ước tính từ ảnh chụp tài khoản và lịch sử giá, không phải khuyến nghị.", warnings: pos.length ? [] : ["Tài khoản không có vị thế mở."],
    margin: { margin_level_pct: level, free_margin: s.equity - s.margin, margin_used_pct_equity: s.margin ? (s.margin / s.equity) * 100 : 0, distance_to_stop_out: s.equity * 0.62, adverse_move_pct_gross: 3.4, stop_out_pct: 50, nominal_leverage: 500,
      status: level == null ? "no_position" : level < 100 ? "margin_call" : level < 300 ? "warn" : "ok" },
    exposure: { positions: pos.length, mode: id.startsWith("mt5") ? "hedging" : "netting", leverage_gross: 4.2, leverage_net: 1.8,
      by_currency: [{ ccy: "USD", net_value: -12400, pct_equity: -98 }, { ccy: "EUR", net_value: 5430, pct_equity: 43 }, { ccy: "XAU", net_value: -2661, pct_equity: -21 }],
      by_symbol: pos.map((p) => ({ symbol: p.symbol, long_lots: p.side === "buy" ? p.volume : 0, short_lots: p.side === "sell" ? p.volume : 0, net_lots: p.side === "buy" ? p.volume : -p.volume, net_value: (p.side === "buy" ? 1 : -1) * p.volume * 100000 * 0.1 })) },
    drawdown: { available: true, day: { pnl_pct: 0.62 }, week: { pnl_pct: -1.4 }, dd_from_peak_pct: -2.1, max_dd_pct: -5.8, underwater: uw },
    var: { available: true, days: 240, coverage_pct: 92, hist: { "95": { var: 215.4, var_pct: 1.7 }, "99": { var: 340, var_pct: 2.7 }, es: { es: 301.2, es_pct: 2.4 } } },
    budget: { status: "warn", items: [
      { key: "daily_loss", label: "Lỗ trong ngày", value: 0.9, limit: 3, unit: "%", used_pct: 30, status: "ok" },
      { key: "dd", label: "Sụt giảm từ đỉnh", value: 2.1, limit: 5, unit: "%", used_pct: 42, status: "ok" },
      { key: "lev", label: "Đòn bẩy hiệu dụng", value: 4.2, limit: 5, unit: "x", used_pct: 84, status: "warn" },
      { key: "ml", label: "Mức margin tối thiểu", value: level ? level / 100 : null, limit: 2, unit: "x", direction: "min", used_pct: 55, status: "ok" } ] },
    stress: [
      { id: "s1", name: "USD tăng mạnh 3% trong 1 ngày", pnl: -612, pnl_pct: -4.9, coverage_pct: 100, missing: [], window: "Kịch bản giả định" },
      { id: "s2", name: "Vàng đảo chiều 2 phiên liên tiếp", pnl: -240, pnl_pct: -1.9, coverage_pct: 100, missing: [], window: "Lịch sử D1" },
      { id: "s3", name: "Tin NFP lệch lớn", pnl: 188, pnl_pct: 1.5, coverage_pct: 90, missing: [], window: "Lịch sử D1" } ],
  };
}

// ---------- nhật ký ----------
const NOTES = { deal: new Map(), day: new Map(), week: new Map() };
function deals(acc) {
  seed = 99 + acc.length; const out = []; const syms = ["EURUSD", "XAUUSD", "GBPUSD", "USDJPY"];
  for (let i = 0; i < 64; i++) {
    const net = +(gauss() * 70 + 6).toFixed(2), sym = syms[i % 4], t = NOW() - (i * 11 + 2) * 3600e3;
    out.push({ ticket: String(100200 + i), symbol: sym, side: i % 3 ? "buy" : "sell", volume: +(0.1 + (i % 5) * 0.1).toFixed(2), time_open: iso(t - (30 + (i % 7) * 25) * 60e3), time_close: iso(t), hold_s: (30 + (i % 7) * 25) * 60,
      net, r: +(net / 40).toFixed(2), group: i % 4 ? "manual" : "EA-Trend", reason: net > 0 ? "tp" : "sl", flags: i % 9 === 0 ? [{ rule: "no_sl" }] : i % 13 === 0 ? [{ rule: "reentry_after_loss" }] : [] });
  }
  return out;
}

function moreGroups(d) {
  const grp = (keyFn, order) => { const m = new Map(); for (const x of d) { const k = keyFn(x); const r = m.get(k) || { key: k, n: 0, net: 0, w: 0 }; r.n++; r.net += x.net; if (x.net > 0) r.w++; m.set(k, r); }
    const rows = (order || [...m.keys()]).map((k) => m.get(k) || { key: k, n: 0, net: 0, w: 0 }); return rows.map((r) => ({ key: r.key, n: r.n, net: +r.net.toFixed(2), win_rate: r.n ? r.w / r.n : null })); };
  const wd = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
  const hr = (x) => new Date(Date.parse(x.time_open) + 7 * 3600e3).getUTCHours();
  const dw = (x) => (new Date(Date.parse(x.time_open) + 7 * 3600e3).getUTCDay() + 6) % 7;
  const sess = (x) => { const h = new Date(x.time_open).getUTCHours(); return h < 7 ? "asia" : h < 13 ? "london" : h < 17 ? "overlap" : h < 21 ? "ny" : "off"; };
  return { hour: grp(hr, Array.from({ length: 24 }, (_, i) => i)), weekday: grp(dw, [0, 1, 2, 3, 4, 5, 6]).map((r) => ({ ...r, label: wd[r.key] })), session: grp(sess, ["asia", "london", "overlap", "ny", "off"]), side: grp((x) => x.side, ["buy", "sell"]) };
}
function journalSummary(acc) {
  const d = deals(acc), wins = d.filter((x) => x.net > 0), loss = d.filter((x) => x.net < 0);
  const net = d.reduce((s, x) => s + x.net, 0), gp = wins.reduce((s, x) => s + x.net, 0), gl = loss.reduce((s, x) => s + x.net, 0);
  let eq = 12000, peak = eq; const pts = [...d].reverse().map((x) => { eq += x.net; peak = Math.max(peak, eq); return { t: x.time_close, equity: +eq.toFixed(2), dd: +(peak - eq).toFixed(2), dd_pct: +(((peak - eq) / peak) * 100).toFixed(2), ticket: x.ticket }; });
  const cal = new Map(); for (const x of d) { const k = x.time_close.slice(0, 10); const c = cal.get(k) || { date: k, net: 0, n: 0 }; c.net = +(c.net + x.net).toFixed(2); c.n++; cal.set(k, c); }
  const by = (key) => { const m = new Map(); for (const x of d) { const r = m.get(x[key]) || { key: x[key], n: 0, net: 0, w: 0 }; r.n++; r.net += x.net; if (x.net > 0) r.w++; m.set(x[key], r); } return [...m.values()].map((r) => ({ key: r.key, n: r.n, net: +r.net.toFixed(2), win_rate: r.w / r.n })).sort((a, b) => b.net - a.net); };
  return { summary: { n: d.length, wins: wins.length, losses: loss.length, breakeven: 0, net: +net.toFixed(2), gross_profit: +gp.toFixed(2), gross_loss: +gl.toFixed(2), win_rate: wins.length / d.length, profit_factor: +(gp / -gl).toFixed(2), expectancy: +(net / d.length).toFixed(2), avg_win: gp / wins.length, avg_loss: gl / loss.length, payoff: 1.2, best: Math.max(...d.map((x) => x.net)), worst: Math.min(...d.map((x) => x.net)), avg_r: 0.18, n_r: d.length },
    equity: { points: pts, max_dd: Math.max(...pts.map((p) => p.dd)), max_dd_pct: Math.max(...pts.map((p) => p.dd_pct)), current_dd: pts[pts.length - 1].dd, base: 12000 }, calendar: [...cal.values()], groups: { symbol: by("symbol"), magic: by("group"), ...moreGroups(d) }, streaks: { max_win_streak: 5, max_loss_streak: 4 }, hold: { avg_s: 5400 }, costs: { total: -42.3 }, notes: ["Dữ liệu mẫu để thử giao diện."] };
}

// ---------- thị trường ----------
const SYMS = [["EURUSD", "Euro / Đô la Mỹ", 5, 1.0861], ["GBPUSD", "Bảng Anh / Đô la Mỹ", 5, 1.2611], ["USDJPY", "Đô la Mỹ / Yên Nhật", 3, 150.214], ["XAUUSD", "Vàng", 2, 2661.9], ["USDCAD", "Đô la Mỹ / Đô la Canada", 5, 1.3652], ["AUDUSD", "Đô la Úc / Đô la Mỹ", 5, 0.6621], ["BTCUSD", "Bitcoin", 1, 68420.5], ["US:AAPL", "Apple", 2, 227.4]];
const TFMIN = { M1: 1, M5: 5, M15: 15, H1: 60, H4: 240, D1: 1440 };
function bars(symbol, tf, limit) {
  const s = SYMS.find((x) => x[0] === symbol) || SYMS[0]; const step = (TFMIN[tf] || 60) * 60e3;
  seed = symbol.length * 131 + step; let c = s[3] * 0.985; const out = [];
  const t0 = Math.floor(NOW() / step) * step - limit * step;
  for (let i = 0; i < limit; i++) { const o = c; c = o * (1 + gauss() * 0.0012 + 0.00005); const h = Math.max(o, c) * (1 + rnd() * 0.0007), l = Math.min(o, c) * (1 - rnd() * 0.0007); out.push({ symbol, tf, ts_open: iso(t0 + i * step), o, h, l, c, v: Math.round(500 + rnd() * 900), source: "x" }); }
  const k = s[3] / out[out.length - 1].c; return out.map((b) => ({ ...b, o: b.o * k, h: b.h * k, l: b.l * k, c: b.c * k }));
}
function analytics(symbol) {
  const mk = (tf) => { const b = bars(symbol, tf, 200), t = b.map((x) => Math.floor(Date.parse(x.ts_open) / 1000)), cl = b.map((x) => x.c);
    const ema = (n) => { let e = cl[0]; const k = 2 / (n + 1); return cl.map((v) => (e = v * k + e * (1 - k))); };
    const e20 = ema(20), e50 = ema(50), e200 = ema(200);
    return { tf, heat: 64, bias: 38, rsi: 61.3, adx: 27.4, stoch_k: 71, atr_pct: 0.12, atr_percentile: 58, ema200_dist_pct: 0.42, bb_pctb: 0.74, macd_hist: 0.0003,
      states: [{ code: "above_ema200", label: "Trên EMA200", tone: "up", rule: "Giá đóng cửa > EMA200" }, { code: "trend_up", label: "Xu hướng tăng", tone: "up", rule: "EMA20 > EMA50 và ADX ≥ 20" }, { code: "mom_bull", label: "Động lượng nghiêng tăng", tone: "up", rule: "RSI > 55" }],
      pivot: { r2: cl[199] * 1.012, r1: cl[199] * 1.006, p: cl[199], s1: cl[199] * 0.994, s2: cl[199] * 0.988 }, series: { t, ema20: e20, ema50: e50, ema200: e200, bb_upper: cl.map((v) => v * 1.004), bb_lower: cl.map((v) => v * 0.996) } }; };
  return { symbol, tfs: { M15: mk("M15"), H1: mk("H1"), H4: mk("H4"), D1: mk("D1") } };
}
const NEWS = [["Fed giữ nguyên lãi suất, phát tín hiệu cắt giảm chậm hơn dự kiến", ["EURUSD", "XAUUSD"], 0.1], ["Vàng lập đỉnh mới khi nhu cầu trú ẩn tăng", ["XAUUSD"], 0.45], ["Yên Nhật yếu đi sau phát biểu của thống đốc ngân hàng trung ương", ["USDJPY"], -0.3], ["Lạm phát khu vực đồng euro hạ nhiệt trong tháng 9", ["EURUSD"], 0.2], ["Bảng Anh chịu áp lực trước dữ liệu việc làm", ["GBPUSD"], -0.25], ["Bitcoin biến động mạnh quanh vùng 68.000 USD", ["BTCUSD"], 0.05]];

// ---------- cảnh báo ----------
let RULES = [{ id: "11111111-1111-4111-8111-111111111111", name: "Margin thấp (MT5 12345678)", enabled: true, logic: "and", status: "active", conditions: [{ type: "account", account_id: "mt5:12345678", metric: "margin_level", op: "lte", value: 200 }], mode: "repeat", cooldown_min: 30, level: "crit", channels: ["ntfy", "log"], note: "", expires_at: null, last_fired_at: iso(NOW() - 2 * 86400e3), fire_count: 2 }];


function briefing(scope, edition) {
  const items = [{ n: 1, kind: "news", title: "Fed giữ nguyên lãi suất, phát tín hiệu cắt giảm chậm hơn dự kiến", url: "https://example.invalid/1", ts: iso(NOW() - 3600e3) },
    { n: 2, kind: "market", title: "VN-Index đóng cửa 1.735 điểm, giảm 0,22%", ts: iso(NOW() - 7200e3) }, { n: 3, kind: "calendar", title: "Doanh số bán lẻ Mỹ công bố 19:30", ts: iso(NOW() + 5400e3) }];
  return { id: "11111111-2222-4333-8444-555555555555", scope, edition, status: "llm", title: scope === "vn" ? "Bản tin thị trường Việt Nam" : "Bản tin thị trường quốc tế", generated_at: iso(NOW() - 1800e3),
    headline: "Thị trường thận trọng chờ số liệu bán lẻ Mỹ, vàng đi ngang vùng đỉnh",
    body: { points: [{ text: "Fed giữ nguyên lãi suất và cho biết lộ trình cắt giảm sẽ chậm hơn kỳ vọng của thị trường.", cites: [1] }, { text: "VN-Index giảm nhẹ 0,22% với số mã giảm nhiều hơn mã tăng.", cites: [2] }],
      watch: [{ text: "Doanh số bán lẻ Mỹ có thể làm giá vàng và USD biến động mạnh.", status: "sắp tới", ts: iso(NOW() + 5400e3), cites: [3] }], mood: { label: "Hơi tích cực", avg: 0.18, n: 120, pos: 52, neg: 31, neu: 37, text: "Tâm lý tin tức nghiêng nhẹ về tích cực trong 24 giờ qua.", cites: [] } },
    context: { items }, quality: {} };
}

export async function handle(kind, method, path, params = {}, body) {
  if (kind === "auth") return authCall(method, path, body);
  await wait(180);
  if (!load()) err(401, "unauthenticated");
  const mine = USERS[load().key].accounts;
  { const rp = await handlePrefs(method, path, body); if (rp !== undefined) return rp; } // /user/client-prefs: mock_prefs.js (lưu localStorage, dùng chung với cài đặt thông báo)
  { const rn = await handleNotif(method, path, params, body, mine); if (rn !== undefined) return rn; }
  let m;
  if (path === "/accounts") return mine.map(snap);
  if (path === "/equity-history") { if (!mine.includes(params.account_id)) err(403, "forbidden"); return equityHistory(params.account_id, params.from); }
  if ((m = /^\/risk\/accounts\/(.+)$/.exec(path))) { const id = decodeURIComponent(m[1]); if (!mine.includes(id)) err(403, "forbidden"); return riskFor(id); }
  if ((m = /^\/journal\/([^/]+)\/(summary|deals|discipline|notes)(?:\/(deal|week|day)\/(.+))?$/.exec(path))) {
    const acc = decodeURIComponent(m[1]); if (!mine.includes(acc)) err(403, "forbidden");
    if (method === "PUT") { NOTES[m[3]].set(decodeURIComponent(m[4]), { kind: m[3], ref: decodeURIComponent(m[4]), ...body, updated_at: iso(NOW()) }); return { ok: true }; }
    if (method === "DELETE") { NOTES[m[3]].delete(decodeURIComponent(m[4])); return { ok: true }; }
    if (m[2] === "summary") { if (acc === "mt4:55555555") return { summary: { n: 0 } }; return journalSummary(acc); }
    if (m[2] === "deals") { const d = deals(acc).map((x) => x); const lim = Number(params.limit) || 20; return { items: d.slice(0, lim), total: d.length, tags: [] }; }
    if (m[2] === "notes") return { items: [...NOTES[params.kind || "deal"].values()] };
    if (m[2] === "discipline") { const d = deals(acc), fl = d.filter((x) => x.flags.length); return { score: 78, n_flagged: fl.length, n_trades: d.length, net_flagged: fl.reduce((s, x) => s + x.net, 0), net_clean: d.filter((x) => !x.flags.length).reduce((s, x) => s + x.net, 0),
      rules: [{ rule: "no_sl", count: 7, net: -120.5 }, { rule: "reentry_after_loss", count: 4, net: -88 }], flagged: fl.slice(0, 6), note: "Phát hiện sau khi lệnh xảy ra, không chặn lệnh." }; }
  }
  if (path === "/risk-windows") {
    const act = { symbol: "XAUUSD", now: iso(NOW()), state: "imminent", in_window: false, currencies: ["USD"], window_start: iso(NOW() + 12 * 60e3), window_end: iso(NOW() + 57 * 60e3), current: [{ title: "Doanh số bán lẻ Mỹ" }], upcoming: [], next_window: null };
    if (params.symbol) return params.symbol === "XAUUSD" ? act : { symbol: params.symbol, now: iso(NOW()), state: "clear", in_window: false, currencies: [], current: [], upcoming: [], next_window: { title: "Biên bản họp FOMC", start: iso(NOW() + 3 * 3600e3), end: iso(NOW() + 4 * 3600e3) } };
    return { generated_at: iso(NOW()), horizon_hours: 6, symbols: [act, { ...act, symbol: "EURUSD", state: "clear", window_start: null, window_end: null, current: [], next_window: { title: "Biên bản họp FOMC", start: iso(NOW() + 3 * 3600e3), end: iso(NOW() + 4 * 3600e3) } }] };
  }
  if (path === "/symbols") return SYMS.map(([symbol, name, precision, last], i) => ({ symbol, name, precision, last, change_pct: +((i % 2 ? -1 : 1) * (0.1 + i * 0.07)).toFixed(2), class: "forex", session_open: true }));
  if (path === "/quotes/latest") { const want = params.symbols ? String(params.symbols).split(",") : null; return SYMS.filter((x) => !want || want.includes(x[0])).map(([symbol, , , last]) => ({ symbol, ts: iso(NOW()), bid: +(last * (1 + (rnd() - 0.5) * 0.0004)).toFixed(5), ask: last, source: "x" })); }
  if (path === "/briefing/latest") return briefing(params.scope || "vn", params.edition || "morning");
  if (path === "/bars") return { items: bars(params.symbol, params.tf, Number(params.limit) || 200).reverse(), limit: 200, offset: 0, count: 200 };
  if ((m = /^\/analytics\/symbol\/(.+)$/.exec(path))) return analytics(decodeURIComponent(m[1]));
  if (path === "/analytics/screener") return { total: 6, items: SYMS.slice(0, 6).map(([symbol], i) => ({ symbol, tf: params.tf || "H1", heat: 80 - i * 8, bias: 60 - i * 20, trend: ["up", "down", "side"][i % 3], momentum: ["bullish", "overbought", "oversold", "neutral", "bearish", "bullish"][i], volatility: ["normal", "squeeze", "high", "low", "normal", "normal"][i], rsi: 48 + i * 5, adx: 18 + i * 4 })) };
  if (path === "/analytics/overview") return { symbols: SYMS.map((s) => s[0]), summary: {} };
  if (path === "/news") return { items: NEWS.map(([title, symbols, sentiment], i) => ({ url: `https://example.invalid/${i}`, title, summary: "Tóm tắt ngắn của bài viết để xem trước giao diện.", published_at: iso(NOW() - (i * 47 + 5) * 60e3), source: "x", symbols, sentiment })), limit: 20, offset: 0, count: NEWS.length };
  if (path === "/calendar") { const base = Date.parse(params.from || new Date().toISOString()); return { items: [["Doanh số bán lẻ", "US", "high", "0.4%", "0.1%", null, 3], ["PMI dịch vụ", "EU", "med", "51.2", "50.8", "51.5", -1], ["Quyết định lãi suất", "UK", "high", "5.00%", "5.00%", null, 5], ["Tồn kho dầu thô", "US", "med", "-1.2M", "0.8M", null, 8]].map(([title, country, impact, forecast, previous, actual, h], i) => ({ event_id: `e${i}`, source: "x", country, title, impact, ts: iso(base + (h + 8) * 3600e3), forecast, previous, actual, extra: actual ? { surprise: { verdict: "good" } } : null })), limit: 300, offset: 0, count: 4 }; }
  if (path === "/user/csrf") return { token: "mock-csrf", ttl_s: 3600 };
  if (path === "/user/rules" && method === "GET") return { items: RULES, limits: { max_rules: 50 } };
  if (path === "/user/rules" && method === "POST") { const r = { id: crypto.randomUUID(), status: "active", fire_count: 0, last_fired_at: null, note: "", ...body }; RULES = [r, ...RULES]; return r; }
  if ((m = /^\/user\/rules\/([0-9a-f-]{36})$/.exec(path))) { if (method === "DELETE") { RULES = RULES.filter((r) => r.id !== m[1]); return { ok: true }; } RULES = RULES.map((r) => (r.id === m[1] ? { ...r, ...body, status: body.enabled ? "active" : "disabled" } : r)); return RULES.find((r) => r.id === m[1]); }
  if (path === "/user/rule-events") return { items: [{ id: 1, ts: iso(NOW() - 2 * 86400e3), rule_name: "Margin thấp (MT5 12345678)", level: "crit", title: "Mức margin còn 186%", body: "Tài khoản mt5:12345678 chạm ngưỡng 200%." }] };
  { const r = await handleToday(method, path, params, body); if (r !== undefined) return r; }
  err(404, "not_found");
}
