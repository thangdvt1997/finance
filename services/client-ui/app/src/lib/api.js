// Lớp gọi API của client-ui. Mọi request đi qua nginx của client-ui:
//   /c/api/v1/*  -> api-gateway (nginx chèn khoá + danh tính đã xác thực; trình duyệt chỉ có cookie phiên HttpOnly)
//   /c/auth/*    -> dịch vụ auth
// Chế độ MOCK (cờ): ?mock=1 trên URL (nhớ trong sessionStorage) hoặc build với VITE_MOCK=1. Mock nạp lười (không vào bundle chính).
import { t } from "./i18n";
export class ApiError extends Error {
  constructor(status, message, detail, retryAfter) {
    super(message);
    this.status = status;
    this.detail = detail;
    this.retryAfter = retryAfter; // giây (nếu máy chủ trả Retry-After / retry_after)
  }
}

const MOCK_KEY = "tc-mock";
function readFlag() {
  try {
    const q = new URLSearchParams(location.search + (location.hash.includes("?") ? "&" + location.hash.split("?")[1] : ""));
    if (q.get("mock") === "1") sessionStorage.setItem(MOCK_KEY, "1");
    if (q.get("mock") === "0") sessionStorage.removeItem(MOCK_KEY);
    return sessionStorage.getItem(MOCK_KEY) === "1";
  } catch { return false; }
}
export const MOCK = import.meta.env.VITE_MOCK === "1" || readFlag();

let mockMod = null;
const mockApi = async (kind, method, path, params, body) => {
  mockMod = mockMod || (await import("./mock.js"));
  return mockMod.handle(kind, method, path, params, body);
};

export const emitUnauth = () => window.dispatchEvent(new CustomEvent("tc-unauth"));

const mapMsg = (st) => ({
  401: t("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."),
  403: t("Bạn không có quyền xem mục này."),
  404: t("Không tìm thấy (hoặc máy chủ chưa hỗ trợ)."),
  429: t("Quá nhiều yêu cầu, đợi vài giây rồi thử lại."),
  502: t("Máy chủ chưa sẵn sàng, thử lại sau ít phút."),
  503: t("Dịch vụ tạm thời không khả dụng."),
  504: t("Máy chủ phản hồi quá chậm."),
}[st]);

export function detailText(d) {
  if (typeof d === "string") return d;
  if (d && typeof d === "object" && !Array.isArray(d) && typeof d.message === "string") return d.message;
  if (Array.isArray(d)) return d.map((x) => `${(x.loc || []).filter((p) => p !== "body").join(".")}: ${x.msg}`).join("; ");
  return "";
}

async function parse(res) {
  const ct = res.headers.get("content-type") || "";
  if (res.status === 204) return { ok: true };
  if (!ct.includes("json")) return { ok: res.ok };
  try { return await res.json(); } catch { return {}; }
}

async function request(base, method, path, { params, body, signal, headers } = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
  const url = `${base}${path}${qs.size ? `?${qs}` : ""}`;
  let res;
  try {
    res = await fetch(url, {
      method, signal, credentials: "same-origin", cache: "no-store",
      headers: { Accept: "application/json", ...(body !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new ApiError(0, t("Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại."));
  }
  const data = await parse(res);
  if (res.ok) return data;
  const ra = Number(res.headers.get("retry-after")) || data?.retry_after || undefined;
  throw new ApiError(res.status, mapMsg(res.status) || t("Lỗi {n} từ máy chủ.", { n: res.status }), data?.detail ?? data, ra);
}

/** GET dữ liệu (gateway /v1). */
export async function api(path, params = {}, signal) {
  if (MOCK) {
    try { return await mockApi("api", "GET", path, params); } catch (e) { if (e.status === 401) emitUnauth(); throw e; }
  }
  try {
    return await request("/c/api/v1", "GET", path, { params, signal });
  } catch (e) {
    if (e.status === 401) emitUnauth();
    throw e;
  }
}

/** Gọi dịch vụ auth (/auth/*). Lỗi 401 KHÔNG phát sự kiện đăng xuất (đăng nhập sai là chuyện bình thường). */
export function auth(method, path, body, signal) {
  if (MOCK) return mockApi("auth", method, path, {}, body);
  return request("/c/auth", method, path, { body, signal });
}

// ===== Ghi cấu hình cá nhân (quy tắc cảnh báo, ghi chú nhật ký). Whitelist ở nginx; CSRF token qua /user/csrf. =====
let csrf = null;
async function getCsrf(force) {
  if (csrf && !force && csrf.exp > Date.now()) return csrf.token;
  const r = await api("/user/csrf");
  csrf = { token: r.token, exp: Date.now() + Math.max(30, (r.ttl_s || 600) - 30) * 1000 };
  return csrf.token;
}
export const resetCsrf = () => { csrf = null; };
const writeErr = (st) => ({
  401: mapMsg(401), 403: t("Không có quyền thực hiện thao tác này."), 404: t("Không tìm thấy (hoặc máy chủ chưa hỗ trợ tính năng này)."),
  409: t("Dữ liệu đã thay đổi ở nơi khác."), 413: t("Dữ liệu quá lớn."), 422: t("Dữ liệu không hợp lệ."), 429: mapMsg(429), 502: mapMsg(502), 503: mapMsg(503),
}[st]);
export async function apiWrite(method, path, body) {
  if (MOCK) return mockApi("api", method, path, {}, body);
  for (let attempt = 0; attempt < 2; attempt++) {
    const token = await getCsrf(attempt > 0);
    try {
      return await request("/c/api/v1", method, path, { body, headers: { "X-CSRF-Token": token } });
    } catch (e) {
      if (e.status === 403 && attempt === 0 && /csrf/i.test(detailText(e.detail))) { csrf = null; continue; }
      if (e.status === 401) emitUnauth();
      if (e.status > 0) {
        const extra = e.status === 422 || e.status === 403 ? detailText(e.detail) : "";
        throw new ApiError(e.status, `${writeErr(e.status) || e.message}${extra ? ` (${extra})` : ""}`, e.detail, e.retryAfter);
      }
      throw e;
    }
  }
}
