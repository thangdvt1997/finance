// Truy vấn + suy diễn dữ liệu cho trang Khách hàng (master). Hợp đồng API: xem đầu lib/clientsApi.js.
import { useMemo } from "react";
import { useInfiniteQuery, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { adminDelete, adminGet, adminPost, fetchMe, gw, useBackendMode } from "./clientsApi";

export const HEALTH_AGE = { online: 120, lag: 900 }; // giây kể từ lần cuối nhận dữ liệu: ≤120 trực tuyến, ≤900 chậm, còn lại mất kết nối
export const LATEST_EA = "1.4.2";

export const STATUS_VN = { pending: "Chờ ghép cặp", active: "Hoạt động", suspended: "Đình chỉ" };
export const HEALTH_VN = { online: "Trực tuyến", lag: "Chậm", offline: "Mất kết nối", pending: "Chờ ghép cặp", suspended: "Đình chỉ", never: "Chưa kết nối" };
export const RISK_VN = { crit: "Vượt ngưỡng", warn: "Gần ngưỡng", ok: "Trong hạn mức", na: "Chưa có dữ liệu" };

const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const ms = (t) => { const x = t ? Date.parse(t) : NaN; return Number.isFinite(x) ? x : null; };

/** acc (auth) + user (auth) -> hồ sơ phẳng cho UI. */
export function normalizeProfile(a, user) {
  return {
    ...a, client_name: a.client_name || a.label || "", last_login_at: a.client_last_login || user?.last_login_at || null,
    locked_until: a.client_locked_until || user?.locked_until || null, failed_attempts: user?.failed_attempts ?? 0, sessions_open: user?.active_sessions ?? 0,
    pairing_pending: a.status === "pending" && !!a.has_pairing, ea_version: a.ea_version ?? null, terminal_build: a.terminal_build ?? null, latency_ms: a.latency_ms ?? null,
  };
}

export function cmpVer(a, b) {
  const x = String(a).split(".").map(Number), y = String(b).split(".").map(Number);
  for (let i = 0; i < Math.max(x.length, y.length); i++) { const d = (x[i] || 0) - (y[i] || 0); if (d) return d; }
  return 0;
}

/** Ghép hồ sơ (auth) + snapshot/risk/cảnh báo (gateway) thành một dòng "fleet". */
export function buildRow(p, snap, risk, alerts, now) {
  const t1 = ms(snap?.ts), t2 = ms(p.last_seen_at);
  const lastData = Math.max(t1 ?? 0, t2 ?? 0) || null;
  const age = lastData ? Math.max(0, (now - lastData) / 1000) : null;
  let health;
  if (p.status === "pending") health = "pending";
  else if (p.status === "suspended") health = "suspended";
  else if (age == null) health = "never";
  else health = age <= HEALTH_AGE.online ? "online" : age <= HEALTH_AGE.lag ? "lag" : "offline";

  const ag = snap?.agent || {};
  const ea_version = p.ea_version || ag.ea || null;
  const terminal_build = p.terminal_build || (ag.build ? String(ag.build) : null);
  const latency_ms = p.latency_ms ?? (ag.rtt_ms || null);

  const equity = num(snap?.equity) ?? num(risk?.equity);
  const balance = num(snap?.balance);
  const positions = snap?.positions || [];
  const floating = positions.length ? positions.reduce((s, x) => s + (x.profit || 0), 0) : null;
  const marginLevel = num(risk?.margin_level) ?? (snap?.margin ? (snap.equity / snap.margin) * 100 : null);
  const dd = num(risk?.dd_from_peak_pct) == null ? null : Math.abs(risk.dd_from_peak_pct);
  const reasons = [];
  let level = "na";
  if (risk || snap) {
    level = "ok";
    if (risk?.budget_status === "crit" || risk?.margin_status === "crit") level = "crit";
    else if (risk?.budget_status === "warn" || risk?.margin_status === "warn") level = "warn";
    if (marginLevel != null && marginLevel < 150) { level = "crit"; reasons.push(`Margin ${marginLevel.toFixed(0)}% < 150%`); }
    else if (marginLevel != null && marginLevel < 300) { if (level === "ok") level = "warn"; reasons.push(`Margin ${marginLevel.toFixed(0)}% < 300%`); }
    if (dd != null && dd >= 10) { level = "crit"; reasons.push(`Drawdown ${dd.toFixed(1)}% ≥ 10%`); }
    else if (dd != null && dd >= 5) { if (level === "ok") level = "warn"; reasons.push(`Drawdown ${dd.toFixed(1)}% ≥ 5%`); }
    if (!reasons.length && level !== "ok") reasons.push("Vượt ngưỡng ngân sách rủi ro");
  }
  const lev = num(risk?.leverage_effective);
  const exposure = equity != null && lev != null ? equity * lev : null;
  const login = String(p.login);
  const mine = (alerts || []).filter((a) => `${a.title} ${a.body || ""} ${a.dedupe_key || ""}`.includes(p.account_id) || `${a.title} ${a.dedupe_key || ""}`.includes(login));
  return {
    ...p, ea_version, terminal_build, latency_ms, health, age, lastData, equity, balance, floating, marginLevel, dd, dayPnlPct: num(risk?.day_pnl_pct), exposure, leverage: lev,
    posCount: positions.length || num(risk?.positions) || 0, positions, riskLevel: level, riskReasons: reasons, lastAlert: mine[0] || null, alertCount: mine.length,
    snapAge: t1 ? Math.max(0, (now - t1) / 1000) : null, eaOutdated: !!ea_version && cmpVer(ea_version, LATEST_EA) < 0,
  };
}

export function useMe() {
  const mode = useBackendMode();
  return useQuery({ queryKey: ["clients-me", mode.pref, mode.fell], queryFn: fetchMe, staleTime: 5 * 60_000, retry: false });
}

/** Danh sách fleet đã ghép. Chạy auth trước (để chế độ auto kịp chuyển sang minh hoạ), rồi dữ liệu gateway. */
export function useFleet() {
  const mode = useBackendMode();
  const q = useQuery({
    queryKey: ["clients-fleet", mode.pref, mode.fell],
    refetchInterval: 15_000, staleTime: 8_000, placeholderData: keepPreviousData, retry: false,
    queryFn: async ({ signal }) => {
      const accs = await adminGet("/accounts");
      const soft = (p) => p.catch(() => null);
      const [users, snaps, risks, alerts] = await Promise.all([soft(adminGet("/users")), soft(gw("/accounts", {}, signal)), soft(gw("/risk/accounts", {}, signal)), soft(gw("/alerts", { limit: 200 }, signal))]);
      const U = new Map((users?.items || []).map((u) => [u.user_id, u]));
      return { profiles: (accs.items || []).map((a) => normalizeProfile(a, U.get(a.client_id))), snaps: snaps || [], risks: risks?.accounts || [], alerts: alerts?.items || [],
        gwOk: { snaps: !!snaps, risks: !!risks, alerts: !!alerts }, at: Date.now() };
    },
  });
  const rows = useMemo(() => {
    const d = q.data; if (!d) return null;
    const S = new Map(d.snaps.map((s) => [s.account_id, s])), R = new Map(d.risks.filter((r) => !r.error).map((r) => [r.account_id, r]));
    return d.profiles.map((p) => buildRow(p, S.get(p.account_id), R.get(p.account_id), d.alerts, d.at));
  }, [q.data]);
  return { ...q, rows, gwOk: q.data?.gwOk };
}

export function summarize(rows) {
  const c = { total: rows.length, online: 0, lag: 0, offline: 0, pending: 0, suspended: 0, never: 0, equity: 0, exposure: 0, crit: 0, warn: 0, ver: {}, server: {} };
  for (const r of rows) {
    c[r.health] = (c[r.health] || 0) + 1;
    if (r.equity != null && r.status !== "suspended") c.equity += r.equity;
    if (r.exposure != null) c.exposure += r.exposure;
    if (r.riskLevel === "crit") c.crit++; else if (r.riskLevel === "warn") c.warn++;
    if (r.ea_version) c.ver[r.ea_version] = (c.ver[r.ea_version] || 0) + 1;
    if (r.server) c.server[r.server] = (c.server[r.server] || 0) + 1;
  }
  c.up = c.online + c.lag;
  c.down = c.offline + c.never;
  return c;
}

const LOGIN_ACTIONS = new Set(["login_ok", "login_fail", "account_locked", "pair_ok", "pair_fail", "password_changed", "password_change_fail", "logout", "logout_all", "session_revoked", "bad_totp"]);
/** Chi tiết một tài khoản: phiên đang mở + lịch sử (đăng nhập / quản trị) từ audit theo target. */
export function useAdminDetail(row) {
  const mode = useBackendMode();
  const id = row?.account_id;
  return useQuery({
    queryKey: ["clients-acc", id, mode.pref, mode.fell], enabled: !!id, staleTime: 5_000, refetchInterval: 20_000, retry: false,
    queryFn: async () => {
      const [ss, au] = await Promise.all([
        row.client_id ? adminGet("/sessions", { user_id: row.client_id, active: true }).catch(() => ({ items: [] })) : { items: [] },
        adminGet("/audit", { target: id, limit: 200 }),
      ]);
      const ev = au.items || [];
      return { sessions: ss.items || [], history: ev.filter((e) => LOGIN_ACTIONS.has(e.action)), events: ev.filter((e) => !LOGIN_ACTIONS.has(e.action)) };
    },
  });
}
export const useJnQuick = (id) => useQuery({ queryKey: ["clients-jn", id, useBackendMode().fell], queryFn: ({ signal }) => gw(`/journal/${encodeURIComponent(id)}/summary`, {}, signal), enabled: !!id, staleTime: 30_000, retry: false });
export const useEquityHist = (id, days = 7) => useQuery({
  queryKey: ["clients-eq", id, days, useBackendMode().fell], enabled: !!id, staleTime: 30_000, retry: false,
  queryFn: ({ signal }) => gw("/equity-history", { account_id: id, from: new Date(Date.now() - days * 86400e3).toISOString().slice(0, 16) + ":00Z", limit: 2000 }, signal),
});

/** Nhật ký kiểm toán. Máy chủ lọc: action, target (khớp đúng), before_id. Còn lại (người thực hiện, tìm nhanh, ngày) lọc trên các trang đã tải. */
export function useAudit(filters = {}, pageSize = 100) {
  const mode = useBackendMode();
  const { actor, q, from, to, ...server } = filters;
  const clientSide = !!(actor || q || from || to);
  const size = clientSide ? 500 : pageSize;
  return useInfiniteQuery({
    queryKey: ["clients-audit", filters, pageSize, mode.pref, mode.fell], staleTime: 10_000, refetchInterval: 30_000, retry: false,
    initialPageParam: null,
    queryFn: async ({ pageParam }) => {
      const r = await adminGet("/audit", { ...server, limit: size, before_id: pageParam || undefined });
      let items = r.items || [];
      const minId = items.length ? items[items.length - 1].id : null;
      const need = (actor || "").toLowerCase(), qq = (q || "").toLowerCase();
      if (actor) items = items.filter((e) => (e.actor_label || "").toLowerCase().includes(need));
      if (qq) items = items.filter((e) => JSON.stringify(e).toLowerCase().includes(qq));
      if (from) items = items.filter((e) => Date.parse(e.ts) >= Date.parse(from));
      if (to) items = items.filter((e) => Date.parse(e.ts) <= Date.parse(to) + 86400e3);
      return { items, next: (r.items || []).length >= size ? minId : null };
    },
    getNextPageParam: (last) => last?.next || undefined,
  });
}

/** Thực thi một hành động quản trị trên auth thật. Trả về dạng phẳng; bí mật (nếu có) chỉ ở giá trị trả về, không vào cache. */
export async function execAction(row, kind) {
  const id = encodeURIComponent(row.account_id), uid = row.client_id;
  switch (kind) {
    case "passcode": { const r = await adminPost(`/accounts/${id}/reset-passcode`); return { passcode: r.passcode }; }
    case "pairing": { const r = await adminPost(`/accounts/${id}/pairing-code`); return { pairing_code: r.pairing_code, pairing_expires_at: r.pairing_expires_at }; }
    case "rotate": {
      const t = await adminPost(`/accounts/${id}/rotate-ea-token`);
      const out = { ea_token: t.ea_token };
      if (row.has_hmac) { try { out.ea_hmac_secret = (await adminPost(`/accounts/${id}/rotate-hmac`)).hmac_secret; } catch (e) { out.warn = `Token đã xoay nhưng chưa xoay được HMAC: ${e.message}`; } }
      return out;
    }
    case "suspend": return adminPost(`/accounts/${id}/suspend`);
    case "activate": return adminPost(`/accounts/${id}/activate`);
    case "logout": if (!uid) throw new Error("Tài khoản chưa có người dùng để đăng xuất."); return adminPost(`/users/${encodeURIComponent(uid)}/revoke-sessions`);
    case "unlock": if (!uid) throw new Error("Tài khoản chưa có người dùng."); return adminPost(`/users/${encodeURIComponent(uid)}/unlock`);
    case "delete": return adminDelete(`/accounts/${id}`);
    case "impersonate": return adminPost("/view-as", { account_id: row.account_id });
    default: throw new Error("Hành động không hỗ trợ.");
  }
}

export function useAdminRun() {
  const qc = useQueryClient();
  const refresh = () => { for (const k of ["clients-fleet", "clients-acc", "clients-audit"]) qc.invalidateQueries({ queryKey: [k] }); };
  return {
    refresh,
    run: async (row, kind) => { const res = await execAction(row, kind); refresh(); return res; },
    create: async (body) => {
      const r = await adminPost("/accounts", { platform: body.platform, login: Number(body.login), server: body.server, label: body.label || "", notes: body.notes || "" });
      refresh();
      const s = r.secrets || {};
      return { account: normalizeProfile(r.account), passcode: s.passcode, pairing_code: s.pairing_code, pairing_expires_at: s.pairing_expires_at, ea_token: s.ea_token, ea_hmac_secret: s.hmac_secret };
    },
  };
}

// ---------- Thông báo cho master (suy diễn phía trình duyệt từ fleet + nhật ký kiểm toán) ----------
export const AUDIT_VN = {
  account_created: "Tạo tài khoản", account_updated: "Sửa tài khoản", account_deleted: "Xoá tài khoản", account_suspended: "Đình chỉ", account_activated: "Kích hoạt",
  passcode_reset: "Cấp lại passcode", ea_token_rotated: "Xoay token EA", ea_hmac_rotated: "Xoay HMAC EA", pairing_code_issued: "Cấp mã ghép cặp", sessions_revoked: "Ép đăng xuất",
  session_revoked: "Thu hồi phiên", view_as: "Xem như khách hàng", login_ok: "Đăng nhập", login_fail: "Đăng nhập sai", account_locked: "Khoá tạm do nhập sai", login_blocked_ip: "Chặn IP đăng nhập sai",
  pair_ok: "Ghép cặp thành công", pair_fail: "Ghép cặp sai mã", password_changed: "Đổi mật khẩu", password_change_fail: "Đổi mật khẩu sai", logout: "Đăng xuất", logout_all: "Đăng xuất mọi phiên",
  user_unlock: "Mở khoá người dùng", user_suspend: "Đình chỉ người dùng", user_activate: "Kích hoạt người dùng", account_linked: "Liên kết tài khoản", account_unlinked: "Gỡ liên kết",
  bad_totp: "Sai mã TOTP", totp_enabled: "Bật TOTP", totp_disabled: "Tắt TOTP",
};
export const AUDIT_TONE = { login_fail: "accent", account_locked: "down", login_blocked_ip: "down", account_deleted: "down", account_suspended: "accent", ea_token_rotated: "accent", ea_hmac_rotated: "accent", passcode_reset: "accent", view_as: "accent", pair_fail: "accent", bad_totp: "accent" };
export const isMasterActor = (l) => /^master/.test(l || "");

export function deriveNotifications(rows, audit, now = Date.now()) {
  const out = [];
  for (const r of rows || []) {
    const name = `${r.label ? r.label + " · " : ""}${r.account_id}`;
    if (r.status === "active" && r.health === "offline" && r.lastData) out.push({ id: `off:${r.account_id}`, ts: r.lastData, level: r.age > 6 * 3600 ? "crit" : "warn", kind: "ea_offline", account_id: r.account_id, title: "EA mất kết nối", text: `${name} không gửi dữ liệu từ lúc ${new Date(r.lastData).toLocaleString("vi-VN")}.` });
    if (r.status === "active" && r.health === "never") out.push({ id: `nev:${r.account_id}`, ts: ms(r.created_at), level: "warn", kind: "ea_never", account_id: r.account_id, title: "EA chưa từng kết nối", text: `${name} đã kích hoạt nhưng chưa nhận dữ liệu.` });
    if (r.status === "pending" && r.pairing_expires_at && ms(r.pairing_expires_at) < now) out.push({ id: `pex:${r.account_id}`, ts: ms(r.pairing_expires_at), level: "warn", kind: "pair_expired", account_id: r.account_id, title: "Mã ghép cặp đã hết hạn", text: `${name} chưa ghép cặp; cấp mã ghép cặp mới.` });
    if (r.riskLevel === "crit") out.push({ id: `rk:${r.account_id}`, ts: r.lastData || now, level: "crit", kind: "risk", account_id: r.account_id, title: "Vượt ngưỡng rủi ro", text: `${name}: ${r.riskReasons.join("; ")}.` });
    if (r.locked_until && ms(r.locked_until) > now) out.push({ id: `lock:${r.account_id}`, ts: now, level: "warn", kind: "locked", account_id: r.account_id, title: "Tài khoản đang bị khoá tạm", text: `${name} bị khoá đến ${new Date(r.locked_until).toLocaleTimeString("vi-VN")} do nhập sai nhiều lần.` });
  }
  const fails = new Map(), oks = new Map();
  for (const a of audit || []) {
    const t = ms(a.ts); if (t == null) continue;
    if (a.action === "login_ok" && !isMasterActor(a.actor_label)) { const l = oks.get(a.target) || []; l.push({ t, ip: a.ip }); oks.set(a.target, l); }
    if (now - t > 24 * 3600e3) continue;
    if (a.action === "login_blocked_ip") out.push({ id: `blk:${a.id}`, ts: t, level: "crit", kind: "ip_blocked", account_id: "", title: "IP bị chặn vì đăng nhập sai liên tục", text: `IP ${a.ip} bị chặn tạm thời.` });
    if (a.action === "account_locked") out.push({ id: `lk:${a.id}`, ts: t, level: "crit", kind: "locked", account_id: a.target, title: "Khoá tạm do nhập sai", text: `${a.target} bị khoá ${a.detail?.minutes ?? "?"} phút (IP ${a.ip}).` });
    if (a.action === "login_fail") { const f = fails.get(a.target) || { n: 0, t, ip: a.ip }; f.n++; f.t = Math.max(f.t, t); fails.set(a.target, f); }
  }
  for (const [acc, f] of fails) if (f.n >= 3) out.push({ id: `fail:${acc}`, ts: f.t, level: f.n >= 5 ? "crit" : "warn", kind: "failed_logins", account_id: acc, title: "Nhiều lần đăng nhập sai", text: `${acc}: ${f.n} lần sai trong 24 giờ qua (IP gần nhất ${f.ip || "—"}).` });
  // Đăng nhập từ IP chưa từng thấy: lượt đăng nhập mới nhất (≤24h) có IP không nằm trong các lượt trước đó (cần ≥2 lượt trước để có "thói quen").
  for (const [acc, l] of oks) {
    l.sort((a, b) => b.t - a.t);
    const [cur, ...prev] = l;
    if (cur && now - cur.t <= 24 * 3600e3 && prev.length >= 2 && cur.ip && !prev.some((x) => x.ip === cur.ip)) out.push({ id: `ip:${acc}:${cur.ip}`, ts: cur.t, level: "warn", kind: "unusual_login", account_id: acc, title: "Đăng nhập từ IP lạ", text: `${acc} đăng nhập từ IP ${cur.ip} chưa từng xuất hiện trong ${prev.length} lượt trước.` });
  }
  const W = { crit: 0, warn: 1, info: 2 };
  return out.sort((a, b) => W[a.level] - W[b.level] || b.ts - a.ts);
}
