// Mọi request đi qua nginx (/api/ -> api-gateway). Khoá API do nginx chèn, trình duyệt không bao giờ thấy.
export class ApiError extends Error {
  constructor(status, message, detail) {
    super(message);
    this.status = status;
    this.detail = detail; // thân lỗi gốc từ máy chủ (422: [{loc,msg}] hoặc chuỗi)
  }
}

// ===== Giảm tải gateway: giới hạn đồng thời + gộp request trùng + tự thử lại khi 429 (tôn trọng Retry-After) =====
const MAX_CONC = 6;
let running = 0;
const waiters = [];
const inflight = new Map();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function slot() {
  if (running >= MAX_CONC) await new Promise((r) => waiters.push(r));
  running++;
}
function release() {
  running--;
  const n = waiters.shift();
  if (n) n();
}
function withSignal(p, signal) {
  if (!signal) return p;
  if (signal.aborted) return Promise.reject(new DOMException("Aborted", "AbortError"));
  return new Promise((resolve, reject) => {
    const onAbort = () => reject(new DOMException("Aborted", "AbortError"));
    signal.addEventListener("abort", onAbort, { once: true });
    p.then(resolve, reject).finally(() => signal.removeEventListener("abort", onAbort));
  });
}
async function fetchJson(url) {
  for (let attempt = 0; ; attempt++) {
    await slot();
    let res;
    try {
      res = await fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" });
    } catch (e) {
      throw new ApiError(0, "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.");
    } finally {
      release();
    }
    if (res.status === 429 && attempt < 3) {
      const ra = Number(res.headers.get("Retry-After"));
      const base = Number.isFinite(ra) && ra > 0 ? Math.min(ra, 10) * 1000 : 800 * 2 ** attempt;
      await sleep(base + Math.random() * 400);
      continue;
    }
    if (!res.ok) {
      const map = {
        401: "Chưa đăng nhập hoặc khoá API không hợp lệ.",
        429: "Quá nhiều yêu cầu, đợi vài giây rồi thử lại.",
        502: "API gateway chưa sẵn sàng.",
        503: "Dịch vụ tạm thời không khả dụng.",
        504: "API gateway phản hồi quá chậm.",
      };
      throw new ApiError(res.status, map[res.status] || `Lỗi ${res.status} từ máy chủ.`);
    }
    return res.json();
  }
}

export function api(path, params = {}, signal) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
  const url = `/api/v1${path}${qs.size ? `?${qs}` : ""}`;
  let p = inflight.get(url);
  if (!p) {
    p = fetchJson(url).finally(() => inflight.delete(url));
    inflight.set(url, p);
  }
  return withSignal(p, signal);
}

export const TFS = ["M1", "M5", "M15", "H1", "H4", "D1"];
export const WATCH = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "VN:VNM", "VN:FPT", "VN:VCB", "US:AAPL"];

// ===== Ghi dữ liệu người dùng (quy tắc cảnh báo, tuỳ chọn). CHỈ các route /user/* được nginx cho phép ghi. =====
let csrf = null;
export async function getCsrf(force) {
  if (csrf && !force && csrf.exp > Date.now()) return csrf.token;
  const r = await api("/user/csrf");
  csrf = { token: r.token, exp: Date.now() + Math.max(30, (r.ttl_s || 600) - 30) * 1000 };
  return csrf.token;
}
function detailText(d) {
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => `${(x.loc || []).filter((p) => p !== "body").join(".")}: ${x.msg}`).join("; ");
  return "";
}
const WRITE_ERR = {
  401: "Chưa đăng nhập hoặc phiên đã hết hạn.",
  403: "Không có quyền thực hiện thao tác này.",
  404: "Không tìm thấy (hoặc máy chủ chưa hỗ trợ tính năng này).",
  409: "Dữ liệu đã thay đổi ở nơi khác.",
  413: "Dữ liệu quá lớn.",
  422: "Dữ liệu không hợp lệ.",
  429: "Quá nhiều yêu cầu, đợi vài giây rồi thử lại.",
  502: "API gateway chưa sẵn sàng.",
  503: "Dịch vụ tạm thời không khả dụng.",
};
export async function apiWrite(method, path, body, opts = {}) {
  const url = `/api/v1${path}`;
  const text = body === undefined ? undefined : JSON.stringify(body);
  if (text && text.length > (opts.maxBytes ?? 15800)) throw new ApiError(413, WRITE_ERR[413]);
  for (let attempt = 0; attempt < 2; attempt++) {
    const token = await getCsrf(attempt > 0);
    let res;
    try {
      res = await fetch(url, {
        method,
        credentials: "same-origin",
        headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRF-Token": token },
        body: text,
      });
    } catch {
      throw new ApiError(0, "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.");
    }
    if (res.ok) return res.status === 204 ? { ok: true } : res.json().catch(() => ({ ok: true }));
    let detail;
    try { detail = (await res.json()).detail; } catch { /* không có thân JSON */ }
    if (res.status === 403 && attempt === 0 && /csrf/i.test(detailText(detail))) { csrf = null; continue; }
    const extra = res.status === 422 || res.status === 403 ? detailText(detail) : "";
    throw new ApiError(res.status, `${WRITE_ERR[res.status] || `Lỗi ${res.status} từ máy chủ.`}${extra ? ` (${extra})` : ""}`, detail);
  }
}
