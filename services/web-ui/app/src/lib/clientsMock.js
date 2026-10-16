// Dữ liệu MINH HOẠ cho trang Khách hàng khi dịch vụ `auth` chưa sẵn sàng (xem lib/clientsApi.js).
// Mô phỏng đúng hình dạng JSON của services/auth (/auth/admin/*) và api-gateway (accounts, risk/accounts, alerts, journal). Trạng thái lưu trong sessionStorage.
import { ApiError } from "./api";

const SK = "clients.mock.v2";
const H = 3600e3, D = 24 * H;
let seed = 7;
const rnd = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
const hex = (n) => Array.from({ length: n }, () => "0123456789abcdef"[Math.floor(Math.random() * 16)]).join("");
const b32 = (n) => Array.from({ length: n }, () => "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"[Math.floor(Math.random() * 32)]).join("");
const uuid = () => `${hex(8)}-${hex(4)}-4${hex(3)}-a${hex(3)}-${hex(12)}`;

const NAMES = ["Nguyễn Văn An", "Trần Thị Bích", "Lê Quang Huy", "Phạm Minh Châu", "Hoàng Gia Bảo", "Vũ Thu Hà", "Đặng Quốc Việt", "Bùi Ngọc Lan", "Đỗ Thanh Tùng", "Ngô Khánh Linh", "Dương Hải Đăng", "Lý Mỹ Duyên", "Phan Anh Khoa", "Trịnh Hoài Nam", "Võ Tuyết Mai", "Đinh Công Sơn"];
const SERVERS = ["Exness-MT5Real8", "ICMarketsSC-MT5-2", "Pepperstone-Edge03", "VantageInternational-Live", "XMGlobal-MT5 5", "FPMarkets-Live2", "Tickmill-Live"];
const VERS = ["1.4.2", "1.4.1", "1.3.9"];

function seedState() {
  const now = Date.now();
  const plan = [
    ["mt5", "online", 2], ["mt5", "online", 4], ["mt4", "online", 3], ["mt5", "online", 9], ["mt5", "online", 6], ["mt4", "online", 11], ["mt5", "online", 5],
    ["mt5", "online", 7], ["mt4", "online", 38], ["mt5", "online", 95], ["mt5", "offline", 3 * 3600], ["mt4", "offline", 26 * 3600], ["mt5", "pending", 0], ["mt4", "pending", 0],
    ["mt5", "suspended", 5 * 86400], ["mt5", "online", 8],
  ];
  const profiles = plan.map(([platform, kind, age], i) => {
    const login = 91004200 + i * 137;
    const created = now - (20 + i * 9) * D;
    const ver = VERS[i % 3 === 2 ? 2 : i % 5 === 4 ? 1 : 0];
    return {
      account_id: `${platform}:${login}`, platform, login, server: SERVERS[i % SERVERS.length], label: ["Chính", "Scalp", "Swing", "Vàng", "Dài hạn", "Thử", "Quỹ A", "Quỹ B"][i % 8] + ` ${i + 1}`,
      client_id: uuid(), client_name: NAMES[i % NAMES.length], status: kind === "pending" ? "pending" : kind === "suspended" ? "suspended" : "active",
      created_at: new Date(created).toISOString(), _age: age, _kind: kind, ea_version: kind === "pending" ? null : ver, terminal_build: kind === "pending" ? null : String(platform === "mt4" ? 1380 + (i % 4) * 22 : 4380 + (i % 4) * 22),
      latency_ms: kind === "online" ? 40 + Math.round(rnd() * 160) + (i === 9 ? 900 : 0) : null, nsess: kind === "online" && i % 3 === 0 ? 1 + (i % 2) : 0,
      last_login_at: kind === "pending" ? null : new Date(now - (1 + i) * H * 5).toISOString(), failed_attempts: i === 5 ? 4 : i === 8 ? 2 : 0, locked_until: i === 5 ? new Date(now + 12 * 60e3).toISOString() : null,
      pairing_pending: kind === "pending", pairing_expires_at: kind === "pending" ? new Date(now + (i === 12 ? 20 : -3) * H).toISOString() : null, notes: i === 1 ? "Khách VIP, ưu tiên hỗ trợ." : "", deleted_at: null,
      equity0: Math.round((4000 + rnd() * 90000) * 100) / 100, lev: Math.round((1 + rnd() * 9) * 10) / 10, mlevel: i === 3 ? 118 : i === 8 ? 165 : Math.round(260 + rnd() * 2400), dd: i === 3 ? 14.2 : i === 9 ? 8.1 : Math.round(rnd() * 42) / 10,
      dayPnl: Math.round((rnd() - 0.45) * 380) / 100, npos: kind === "online" ? 1 + Math.floor(rnd() * 5) : 0,
    };
  });
  const id5 = profiles[5].account_id, id3 = profiles[3].account_id, id2 = profiles[2].account_id, id14 = profiles[14].account_id;
  const audit = [];
  const A = (ts, actor, action, target, ip, detail) => audit.push({ id: 0, ts: new Date(ts).toISOString(), actor_user_id: null, actor_label: actor, action, target, ip, detail: detail || {} });
  profiles.forEach((p, i) => {
    A(Date.parse(p.created_at), "master:admin", "account_created", p.account_id, "<HOST_IP>", { platform: p.platform, server: p.server });
    if (p._kind !== "pending") {
      A(Date.parse(p.created_at) + 3 * H, p.account_id, "pair_ok", p.account_id, "42.115.8." + (10 + i), {});
      for (let k = 0; k < 5; k++) A(now - (k * 29 + i) * H, p.account_id, "login_ok", p.account_id, k === 0 && i === 3 ? "<HOST_IP>" : `42.115.8.${10 + i}`, { role: "client" });
    }
  });
  for (let k = 0; k < 4; k++) A(now - (50 - k) * 60e3, id5, "login_fail", id5, "<HOST_IP>", { reason: "bad_secret" });
  A(now - 46 * 60e3, id5, "account_locked", id5, "<HOST_IP>", { minutes: 15 });
  A(now - 20 * H, "master:admin", "passcode_reset", id2, "<HOST_IP>", {});
  A(now - 30 * H, "master:admin", "ea_token_rotated", id2, "<HOST_IP>", {});
  A(now - 5 * D, "master:admin", "account_suspended", id14, "<HOST_IP>", {});
  audit.sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts)).forEach((r, k, arr) => { r.id = arr.length - k; });
  const sess = {};
  profiles.forEach((p, i) => {
    sess[p.account_id] = Array.from({ length: p.nsess }, (_, k) => ({ id: hex(64), user_id: p.client_id, login: p.account_id, role: "client", created_at: new Date(now - (k + 1) * H).toISOString(), last_seen_at: new Date(now - (k + 1) * 4 * 60e3).toISOString(),
      expires_at: new Date(now + 6 * D).toISOString(), ip: `42.115.8.${10 + i}`, user_agent: k ? "Safari · iPhone" : "Chrome 128 · Windows", revoked: false, current: false }));
  });
  return { profiles, audit, sess };
}

let S = null;
function save() { try { sessionStorage.setItem(SK, JSON.stringify(S)); } catch { /* bỏ qua */ } }
function st() {
  if (S) return S;
  try { const r = sessionStorage.getItem(SK); if (r) { S = JSON.parse(r); return S; } } catch { /* bỏ qua */ }
  S = seedState(); save(); return S;
}
export function resetMock() { try { sessionStorage.removeItem(SK); sessionStorage.removeItem("clients.mock.v1"); } catch { /* bỏ qua */ } S = null; }

const ageOf = (p) => (p._kind === "online" ? p._age + ((Math.floor(Date.now() / 5000) * 7 + p.login) % 9) : p._age);
const lastSeen = (p) => (p._kind === "pending" ? null : new Date(Date.now() - ageOf(p) * 1000).toISOString());
/** Hình dạng đúng `AuthService._acc_out` (+ trường tuỳ chọn ea_version/terminal_build/latency_ms). */
const pub = (p) => ({
  account_id: p.account_id, platform: p.platform, login: p.login, server: p.server, label: p.label, client_id: p.client_id, status: p.status, created_at: p.created_at, last_seen_at: lastSeen(p), notes: p.notes,
  pairing_expires_at: p.pairing_expires_at, has_pairing: !!p.pairing_pending, has_ea_token: true, has_hmac: true, client_login: p.account_id, client_name: p.client_name, client_status: p.status === "suspended" ? "suspended" : "active",
  client_must_change: !!p.pairing_pending, client_last_login: p.last_login_at, client_locked_until: p.locked_until, ea_version: p.ea_version, terminal_build: p.terminal_build, latency_ms: p.latency_ms,
});
const userOf = (p) => ({ user_id: p.client_id, role: "client", login_key: p.account_id, display_name: p.client_name, status: p.status === "suspended" ? "suspended" : "active", must_change_password: !!p.pairing_pending, totp_enabled: false,
  failed_attempts: p.failed_attempts, locked_until: p.locked_until, created_at: p.created_at, last_login_at: p.last_login_at, accounts: [p.account_id], active_sessions: (st().sess[p.account_id] || []).length });
const getP = (id) => { const p = st().profiles.find((x) => x.account_id === id && !x.deleted_at); if (!p) throw new ApiError(404, "Không có tài khoản này"); return p; };
function log(action, target, detail) {
  const s = st(); const id = (s.audit[0]?.id || 0) + 1;
  s.audit.unshift({ id, ts: new Date().toISOString(), actor_user_id: null, actor_label: "master:admin", action, target, ip: "<HOST_IP>", detail: detail || {} }); save();
}

export async function mockAdmin(method, path, { params, body } = {}) {
  await new Promise((r) => setTimeout(r, 120));
  const s = st();
  let m;
  if (method === "GET" && path === "/admin/accounts") return { items: s.profiles.filter((p) => !p.deleted_at).map(pub) };
  if (method === "GET" && path === "/admin/users") return { items: s.profiles.filter((p) => !p.deleted_at).map(userOf) };
  if (method === "GET" && path === "/admin/sessions") {
    const p = s.profiles.find((x) => x.client_id === params?.user_id);
    return { items: p ? s.sess[p.account_id] || [] : Object.values(s.sess).flat() };
  }
  if (method === "GET" && (m = path.match(/^\/admin\/accounts\/([^/]+)$/))) return pub(getP(decodeURIComponent(m[1])));
  if (method === "GET" && path === "/admin/audit") {
    const f = params || {};
    let rows = s.audit.slice();
    if (f.action) rows = rows.filter((r) => r.action === f.action);
    if (f.target) rows = rows.filter((r) => r.target === f.target);
    if (f.before_id) rows = rows.filter((r) => r.id < Number(f.before_id));
    return { items: rows.slice(0, Number(f.limit) || 100) };
  }
  if (method === "POST" && path === "/admin/accounts") {
    const b = body || {};
    if (!/^mt[45]$/.test(b.platform) || !(Number(b.login) > 0) || !/^[\w .:\-/()]{0,64}$/.test(b.server || "")) throw new ApiError(422, "Dữ liệu tài khoản không hợp lệ");
    const id = `${b.platform}:${b.login}`;
    if (s.profiles.some((p) => p.account_id === id && !p.deleted_at)) throw new ApiError(409, "Tài khoản (nền tảng + số + máy chủ) đã tồn tại");
    const now = Date.now();
    const p = { account_id: id, platform: b.platform, login: Number(b.login), server: b.server || "", label: b.label || "", client_id: uuid(), client_name: b.label || id, status: "pending", created_at: new Date(now).toISOString(), _age: 0, _kind: "pending",
      ea_version: null, terminal_build: null, latency_ms: null, nsess: 0, last_login_at: null, failed_attempts: 0, locked_until: null, pairing_pending: true, pairing_expires_at: new Date(now + 7 * D).toISOString(), notes: b.notes || "", deleted_at: null, equity0: 0, lev: 0, mlevel: 0, dd: 0, dayPnl: 0, npos: 0 };
    s.profiles.unshift(p); s.sess[id] = []; log("account_created", id, { platform: b.platform, server: b.server || "" });
    return { account: pub(p), secrets: { passcode: `${b32(4)}-${b32(4)}-${b32(4)}`, pairing_code: `${Math.floor(100000 + Math.random() * 900000)}`, pairing_expires_at: p.pairing_expires_at, ea_token: `eat_${hex(40)}`, hmac_secret: hex(48), note: "Chỉ hiển thị MỘT lần." } };
  }
  if (method === "DELETE" && (m = path.match(/^\/admin\/accounts\/([^/]+)$/))) {
    const p = getP(decodeURIComponent(m[1])); p.deleted_at = new Date().toISOString(); log("account_deleted", p.account_id, { user_deleted: true });
    return { account_id: p.account_id, client_id: p.client_id, user_deleted: true };
  }
  if (method === "POST" && (m = path.match(/^\/admin\/accounts\/([^/]+)\/(suspend|activate|reset-passcode|rotate-ea-token|rotate-hmac|pairing-code)$/))) {
    const p = getP(decodeURIComponent(m[1])); const a = m[2];
    if (a === "suspend") { p.status = "suspended"; s.sess[p.account_id] = []; log("account_suspended", p.account_id); return pub(p); }
    if (a === "activate") { p.status = p._kind === "pending" ? "pending" : "active"; log("account_activated", p.account_id); return pub(p); }
    if (a === "reset-passcode") { p.failed_attempts = 0; p.locked_until = null; s.sess[p.account_id] = []; log("passcode_reset", p.account_id); return { passcode: `${b32(4)}-${b32(4)}-${b32(4)}`, note: "Chỉ hiển thị MỘT lần." }; }
    if (a === "rotate-ea-token") { log("ea_token_rotated", p.account_id); return { ea_token: `eat_${hex(40)}`, note: "Token cũ vô hiệu ngay." }; }
    if (a === "rotate-hmac") { log("ea_hmac_rotated", p.account_id); return { hmac_secret: hex(48), note: "Secret cũ vô hiệu ngay." }; }
    p.pairing_pending = true; p.pairing_expires_at = new Date(Date.now() + 7 * D).toISOString(); log("pairing_code_issued", p.account_id);
    return { pairing_code: `${Math.floor(100000 + Math.random() * 900000)}`, pairing_expires_at: p.pairing_expires_at };
  }
  if (method === "POST" && (m = path.match(/^\/admin\/users\/([^/]+)\/(unlock|revoke-sessions|suspend|activate)$/))) {
    const p = s.profiles.find((x) => x.client_id === decodeURIComponent(m[1])); if (!p) throw new ApiError(404, "Không có người dùng này");
    if (m[2] === "revoke-sessions") { const n = (s.sess[p.account_id] || []).length; s.sess[p.account_id] = []; log("sessions_revoked", p.account_id, { n }); return { revoked: n }; }
    if (m[2] === "unlock") { p.failed_attempts = 0; p.locked_until = null; log("user_unlock", p.account_id); return { ok: true }; }
    log(`user_${m[2]}`, p.account_id); return { ok: true };
  }
  if (method === "POST" && path === "/admin/view-as") { getP(body?.account_id); log("view_as", body.account_id); return { ok: true }; }
  throw new ApiError(404, "Không tìm thấy.");
}

// ===== Dữ liệu kiểu api-gateway cho tài khoản minh hoạ =====
const live = () => st().profiles.filter((p) => !p.deleted_at && p._kind !== "pending");
const POS = ["EURUSD", "XAUUSD", "GBPJPY", "USDJPY", "NAS100", "BTCUSD"];
function positions(p) {
  return Array.from({ length: p.npos }, (_, k) => ({ ticket: 7000000 + (p.login % 997) * 10 + k, symbol: POS[(p.login + k) % POS.length], type: (p.login + k) % 3 === 0 ? 1 : 0, volume: [0.1, 0.2, 0.5, 1, 0.05][(p.login + k) % 5],
    price_open: 1.0825 + k * 0.1, price_current: 1.0838 + k * 0.1, sl: 0, tp: 0, profit: Math.round((((p.login + k * 31) % 200) - 70) * 100) / 100, swap: -0.4, time_open: new Date(Date.now() - (k + 1) * 3 * H).toISOString() }));
}
export function mockGateway(path, params = {}) {
  let m;
  const ps = live();
  if (path === "/accounts") return Promise.resolve(ps.map((p) => ({ account_id: p.account_id, platform: p.platform, ts: lastSeen(p), balance: p.equity0, equity: Math.round(p.equity0 * (1 + p.dayPnl / 100) * 100) / 100,
    margin: Math.round(((p.equity0 * (1 + p.dayPnl / 100)) / (p.mlevel / 100)) * 100) / 100, positions: positions(p), agent: { ea: p.ea_version, build: Number(p.terminal_build), company: p.server.split(/[-_ ]/)[0], rtt_ms: p.latency_ms || 0, fail: 0 } })));
  if (path === "/risk/accounts") return Promise.resolve({ accounts: ps.map((p) => ({ account_id: p.account_id, kind: "mt", platform: p.platform, currency: "USD", name: null, equity: p.equity0, ts: lastSeen(p), margin_level: p.npos ? p.mlevel : null,
    margin_status: p.mlevel < 150 ? "crit" : p.mlevel < 300 ? "warn" : "ok", leverage_effective: p.lev, positions: p.npos, day_pnl_pct: p.dayPnl, dd_from_peak_pct: -p.dd, max_dd_pct: -(p.dd + 3),
    budget_status: p.dd > 10 || p.mlevel < 150 ? "crit" : p.dd > 5 || p.mlevel < 300 ? "warn" : "ok", warnings: [], stale: ageOf(p) > 900 })) });
  if (path === "/alerts") {
    const now = Date.now(); const items = [];
    ps.forEach((p, i) => {
      if (p.mlevel < 300) items.push({ id: 100 + i, ts: new Date(now - (i + 1) * 17 * 60e3).toISOString(), level: p.mlevel < 150 ? "crit" : "warn", title: `Margin level ${p.account_id} dưới ${p.mlevel < 150 ? 150 : 300}%`, body: `Equity/Margin = ${p.mlevel}%.`, tags: ["account", "margin"], dedupe_key: `margin:${p.account_id}`, delivered: true });
      if (p._kind === "offline") items.push({ id: 200 + i, ts: new Date(now - ageOf(p) * 1000 + 300e3).toISOString(), level: "crit", title: `Mất kết nối tài khoản ${p.account_id}`, body: "Không nhận snapshot.", tags: ["ea"], dedupe_key: `hb:${p.account_id}`, delivered: true });
      if (p.dd > 5) items.push({ id: 300 + i, ts: new Date(now - (i + 2) * 41 * 60e3).toISOString(), level: p.dd > 10 ? "crit" : "warn", title: `Drawdown ${p.account_id} đạt ${p.dd}%`, body: null, tags: ["account", "drawdown"], dedupe_key: `dd:${p.account_id}`, delivered: true });
    });
    items.sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts));
    return Promise.resolve({ items, limit: 200, offset: 0, count: items.length });
  }
  if ((m = path.match(/^\/journal\/([^/]+)\/summary$/))) {
    const p = ps.find((x) => x.account_id === decodeURIComponent(m[1])); if (!p) return Promise.reject(new ApiError(404, "Không có nhật ký."));
    const n = 20 + (p.login % 60), wr = 0.38 + (p.login % 30) / 100, wins = Math.round(n * wr);
    return Promise.resolve({ n, wins, losses: n - wins, breakeven: 0, win_rate: wr, net: Math.round(((p.equity0 * (p.dayPnl + 1.2)) / 100) * 100) / 100, profit_factor: 0.9 + (p.login % 17) / 10, best: 410, worst: -260 });
  }
  if (path === "/equity-history") {
    const p = ps.find((x) => x.account_id === params.account_id); if (!p) return Promise.resolve([]);
    const n = 96; let v = p.equity0 * 0.96; const out = [];
    for (let i = 0; i < n; i++) { v += (Math.sin(i / 7 + p.login) + (i / n) * 0.9) * p.equity0 * 0.0016; out.push({ ts: new Date(Date.now() - (n - i) * 30 * 60e3).toISOString(), equity: Math.round(v * 100) / 100, balance: p.equity0 }); }
    return Promise.resolve(out);
  }
  return Promise.reject(new ApiError(404, "Không tìm thấy."));
}
