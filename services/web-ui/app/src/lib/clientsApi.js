// Lớp API cho trang "Khách hàng" (master). Gọi dịch vụ `auth` (services/auth) qua nginx: /auth/* (cookie phiên master; CSRF = Origin==Host do auth + nginx kiểm tra).
// Hợp đồng THẬT (services/auth/src/auth/app.py):
//   GET  /auth/me                                     GET  /auth/admin/accounts            -> {items:[acc]}      GET /auth/admin/accounts/{id} -> acc
//   POST /auth/admin/accounts {platform,login:int,server,label,notes} -> 201 {account, secrets:{passcode,pairing_code,pairing_expires_at,ea_token,hmac_secret}}
//   POST /auth/admin/accounts/{id}/(suspend|activate|reset-passcode|rotate-ea-token|rotate-hmac|pairing-code)      DELETE /auth/admin/accounts/{id}
//   GET  /auth/admin/users -> {items:[{user_id,login_key,display_name,status,failed_attempts,locked_until,active_sessions,accounts[]...}]}
//   POST /auth/admin/users/{uid}/(unlock|revoke-sessions|suspend|activate)       GET /auth/admin/sessions?user_id= -> {items:[{id,created_at,last_seen_at,ip,user_agent}]}
//   GET  /auth/admin/audit?limit&action&before_id&target -> {items:[{id,ts,actor_user_id,actor_label,action,target,ip,detail}]}      POST /auth/admin/view-as {account_id}
// acc = {account_id,platform,login,server,label,client_id,status:"pending|active|suspended",created_at,last_seen_at,notes,pairing_expires_at,has_pairing,has_ea_token,has_hmac,client_name,client_status,client_last_login,client_locked_until}
// (tuỳ chọn, khi mt-bridge lộ ra: ea_version, terminal_build, latency_ms; hoặc snapshot gateway có `agent:{ea,build,company,rtt_ms}`).
// Số liệu tài khoản (equity, vị thế, rủi ro, cảnh báo, nhật ký) lấy từ api-gateway (/v1/accounts, /v1/risk/accounts, /v1/alerts, /v1/journal/*).
//
// Chế độ: "auto" (mặc định: gọi thật; nếu dịch vụ auth chưa sẵn sàng -> tự dùng DỮ LIỆU MINH HOẠ + banner), "mock" (ép minh hoạ), "real" (ép thật).
// Đổi bằng ?mock=1 / ?mock=0 trên URL hoặc localStorage["clients.mode"].
import { useSyncExternalStore } from "react";
import { api, ApiError } from "./api";
import { mockAdmin, mockGateway } from "./clientsMock";
import { getViewAs } from "./fleetApi";

const KEY = "clients.mode";
const readMode = () => { try { return localStorage.getItem(KEY) || "auto"; } catch { return "auto"; } };
let state = { pref: readMode(), fell: false };
const subs = new Set();
const emit = (p) => { state = { ...state, ...p }; subs.forEach((f) => f()); };
export const getMode = () => state;
export const useBackendMode = () => useSyncExternalStore((f) => { subs.add(f); return () => subs.delete(f); }, () => state);
export const isMock = () => state.pref === "mock" || (state.pref === "auto" && state.fell);
export function setModePref(p) { try { localStorage.setItem(KEY, p); } catch { /* bỏ qua */ } emit({ pref: p, fell: false }); }
try {
  const m = /[?&]mock=([01])/.exec(location.search + location.hash);
  if (m) { localStorage.setItem(KEY, m[1] === "1" ? "mock" : "real"); state = { ...state, pref: m[1] === "1" ? "mock" : "real" }; }
} catch { /* bỏ qua */ }

const FALLBACK = new Set([0, 404, 405, 502, 503, 504]); // "chưa có dịch vụ auth" -> minh hoạ (chỉ khi pref=auto)

const ERR = {
  400: "Yêu cầu không hợp lệ.", 401: "Chưa đăng nhập master hoặc phiên đã hết hạn.", 403: "Chỉ master mới có quyền thực hiện thao tác này.", 404: "Không tìm thấy.",
  409: "Xung đột dữ liệu (đã tồn tại hoặc vừa thay đổi).", 413: "Dữ liệu quá lớn.", 422: "Dữ liệu không hợp lệ.", 429: "Quá nhiều yêu cầu, đợi vài giây rồi thử lại.",
  502: "Dịch vụ xác thực chưa sẵn sàng.", 503: "Dịch vụ xác thực tạm thời không khả dụng.",
};
const dtext = (d) => (typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => `${(x.loc || []).filter((p) => p !== "body").join(".")}: ${x.msg}`).join("; ") : "");

async function realFetch(method, path, { params, body } = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
  const url = `/auth${path}${qs.size ? `?${qs}` : ""}`;
  const headers = { Accept: "application/json" };
  const hasBody = method === "POST";
  if (hasBody) headers["Content-Type"] = "application/json";
  let res;
  try { res = await fetch(url, { method, credentials: "same-origin", headers, body: hasBody ? JSON.stringify(body || {}) : undefined }); }
  catch { throw new ApiError(0, "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại."); }
  if (res.ok) {
    if (res.status === 204) return { ok: true };
    const ct = res.headers.get("content-type") || "";
    if (!ct.includes("json")) throw new ApiError(404, ERR[404]);   // nginx trả HTML (SPA) khi route chưa mở
    return res.json();
  }
  let detail; try { detail = (await res.json()).detail; } catch { /* không có JSON */ }
  const extra = dtext(detail);
  throw new ApiError(res.status, `${ERR[res.status] || `Lỗi ${res.status} từ máy chủ.`}${extra && ![404, 401].includes(res.status) ? ` (${extra})` : ""}`, detail);
}

/** Gọi API auth. Chế độ auto: GET lỗi "chưa có dịch vụ" -> chuyển sang minh hoạ (một chiều đến khi tải lại). */
export async function admin(method, path, opt = {}) {
  if (method !== "GET" && getViewAs()) throw new ApiError(0, "Đang xem như khách: mọi thao tác ghi bị khoá. Bấm “Kết thúc” trên thanh cam để quay lại."); // khoá ghi khi xem-như-khách (server vẫn là lớp thật)
  if (isMock()) return mockAdmin(method, path, opt);
  try {
    return await realFetch(method, path, opt);
  } catch (e) {
    if (state.pref === "auto" && e instanceof ApiError && FALLBACK.has(e.status) && method === "GET") {
      emit({ fell: true });
      return mockAdmin(method, path, opt);
    }
    throw e;
  }
}
export const adminGet = (path, params) => admin("GET", `/admin${path}`, { params });
export const adminPost = (path, body) => admin("POST", `/admin${path}`, { body });
export const adminDelete = (path) => admin("DELETE", `/admin${path}`);

/** Dữ liệu tài khoản từ api-gateway (thật) hoặc minh hoạ. */
export function gw(path, params, signal) {
  return isMock() ? mockGateway(path, params) : api(path, params, signal);
}

/** Vai trò hiện tại. /auth/me chưa có phiên (đang đi basic-auth quản trị) -> coi là master "legacy". */
export async function fetchMe() {
  if (isMock()) return { user_id: "mock-master", role: "master", display_name: "Master (minh hoạ)", accounts: [] };
  try {
    const r = await fetch("/auth/me", { credentials: "same-origin", headers: { Accept: "application/json" } });
    if (r.ok && (r.headers.get("content-type") || "").includes("json")) { const j = await r.json(); if (j && j.role) return j; }
  } catch { /* chưa có dịch vụ auth */ }
  return { user_id: "legacy-admin", role: "master", display_name: "Quản trị (basic auth)", accounts: [], legacy: true };
}

/** URL EA gọi tới (BridgeUrl). Mặc định = origin hiện tại + /ingest/v1; master có thể chỉnh và nhớ trên trình duyệt này. */
export const getBridgeUrl = () => { try { return localStorage.getItem("clients.bridge_url") || `${location.origin}/ingest/v1`; } catch { return `${location.origin}/ingest/v1`; } };
export const setBridgeUrl = (u) => { try { localStorage.setItem("clients.bridge_url", u); } catch { /* bỏ qua */ } };
