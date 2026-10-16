// Lớp API quản trị đội tài khoản (docs/FLEET_MGMT.md). KHÔNG có dữ liệu minh hoạ: lỗi thật được ném ra để UI hiện trạng thái lỗi / "chưa khả dụng".
// Gọi qua nginx: /auth/admin/* (cookie phiên HttpOnly; CSRF = Origin==Host do trình duyệt tự gửi). Chỉ ĐỌC/QUẢN TRỊ — không có đường đặt lệnh.
import { useSyncExternalStore } from "react";

export class FleetError extends Error {
  constructor(status, message, code, detail) {
    super(message);
    this.status = status;
    this.code = code || "";   // totp_required | view_as_lock | unavailable | forbidden | network | ...
    this.detail = detail;
  }
}

const dtext = (d) => {
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => `${(x.loc || []).filter((p) => p !== "body").join(".")}: ${x.msg}`).join("; ");
  if (d && typeof d === "object") return d.message || d.error || d.code || "";
  return "";
};

const BASE_ERR = {
  400: "Yêu cầu không hợp lệ.", 401: "Phiên đăng nhập đã hết hạn — tải lại trang để đăng nhập lại.", 403: "Bạn không có quyền thực hiện thao tác này (hoặc ngoài phạm vi được giao).",
  404: "Không tìm thấy hoặc máy chủ chưa hỗ trợ mục này.", 405: "Máy chủ chưa mở thao tác này.", 409: "Dữ liệu vừa thay đổi hoặc đã tồn tại.", 413: "Dữ liệu quá lớn.", 422: "Dữ liệu không hợp lệ.",
  429: "Thao tác quá nhanh, đợi vài giây rồi thử lại.", 502: "Dịch vụ chưa sẵn sàng.", 503: "Dịch vụ tạm thời không khả dụng.", 504: "Dịch vụ phản hồi quá chậm.",
};

// ----- Chế độ "xem như khách": kho dùng chung (banner + khoá thao tác ghi) -----
let VA = { grant: null, loaded: false };
const vsubs = new Set();
const vemit = (p) => { VA = { ...VA, ...p }; vsubs.forEach((f) => f()); };
export const getViewAs = () => VA.grant;
export const setViewAs = (grant) => vemit({ grant, loaded: true });
export const useViewAsGrant = () => useSyncExternalStore((f) => { vsubs.add(f); return () => vsubs.delete(f); }, () => VA.grant, () => VA.grant);

export const normGrant = (r) => {
  const g = Array.isArray(r) ? r[0] : r?.items ? r.items[0] : r?.grant_id ? r : r?.grant || null;
  return g && g.grant_id ? { grant_id: g.grant_id, account_id: g.account_id, expires_at: g.expires_at, reason: g.reason || "" } : null;
};
/** Kết thúc phiên xem như khách (gọi máy chủ, bỏ banner, làm mới dữ liệu, về Đội tài khoản nếu đang ở màn hình xem). */
export async function endViewAs(g, qc) {
  try { if (g?.grant_id) await fx("POST", "/view-as/end", { body: { grant_id: g.grant_id } }); } catch { /* đã hết hạn: bỏ qua */ }
  setViewAs(null);
  qc?.invalidateQueries({ queryKey: ["fl"] });
  if (location.hash.startsWith("#/khach-hang/xem/")) location.hash = "#/doi-tai-khoan";
}

// ----- Trình hướng dẫn bật TOTP: mở từ bất cứ đâu -----
let UI = { totp: false };
const usubs = new Set();
export const openTotpWizard = () => { UI = { ...UI, totp: true }; usubs.forEach((f) => f()); };
export const closeTotpWizard = () => { UI = { ...UI, totp: false }; usubs.forEach((f) => f()); };
export const useTotpWizardOpen = () => useSyncExternalStore((f) => { usubs.add(f); return () => usubs.delete(f); }, () => UI.totp, () => UI.totp);

/**
 * Gọi API. path tính từ gốc `root` (mặc định /auth/admin). Trả JSON. Lỗi -> FleetError (status, code, message tiếng Việt).
 * Khi đang xem như khách: mọi thao tác ghi (trừ /view-as*) bị chặn ngay ở UI (server vẫn là lớp bảo mật thật).
 */
export async function fx(method, path, { params, body, root = "/auth/admin", signal } = {}) {
  if (method !== "GET" && VA.grant && !(root === "/auth/admin" && /^\/view-as/.test(path))) {
    throw new FleetError(0, "Đang ở chế độ xem như khách: mọi thao tác ghi bị khoá. Bấm “Kết thúc” trên thanh cam để quay lại.", "view_as_lock");
  }
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
  const url = `${root}${path}${qs.size ? `?${qs}` : ""}`;
  const headers = { Accept: "application/json" };
  const hasBody = body !== undefined;
  if (hasBody) headers["Content-Type"] = "application/json";
  let res;
  try { res = await fetch(url, { method, signal, credentials: "same-origin", headers, body: hasBody ? JSON.stringify(body) : undefined }); }
  catch (e) {
    if (e?.name === "AbortError") throw e;
    throw new FleetError(0, "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.", "network");
  }
  if (res.ok) {
    if (res.status === 204) return { ok: true };
    const ct = res.headers.get("content-type") || "";
    if (!ct.includes("json")) throw new FleetError(404, BASE_ERR[404], "unavailable"); // nginx trả HTML (SPA) khi route chưa mở
    return res.json();
  }
  let detail, flag = false; try { const j = await res.json(); detail = j.detail; flag = !!j.totp_required; } catch { /* không có JSON */ }
  const text = dtext(detail);
  if (res.status === 403 && (flag || /totp_required/.test(text))) {
    throw new FleetError(403, "Thao tác nhạy cảm cần bật xác thực hai bước (TOTP) cho tài khoản master. Bật TOTP rồi thử lại.", "totp_required", detail);
  }
  const code = res.status === 404 || res.status === 405 ? "unavailable" : res.status === 403 ? "forbidden" : "";
  const extra = text && ![401, 404, 405, 502, 503, 504].includes(res.status) ? ` (${text})` : "";
  throw new FleetError(res.status, `${BASE_ERR[res.status] || `Lỗi ${res.status} từ máy chủ.`}${extra}`, code, detail);
}
export const fget = (path, params, opt) => fx("GET", path, { params, ...opt });
export const fpost = (path, body, opt) => fx("POST", path, { body: body ?? {}, ...opt });
export const fput = (path, body, opt) => fx("PUT", path, { body: body ?? {}, ...opt });
export const fpatch = (path, body, opt) => fx("PATCH", path, { body: body ?? {}, ...opt });
export const fdel = (path, opt) => fx("DELETE", path, opt);
/** API không thuộc /auth/admin (vd /auth/sessions, /auth/totp/*). */
export const authGet = (path, params) => fx("GET", path, { params, root: "/auth" });
export const authPost = (path, body) => fx("POST", path, { body: body ?? {}, root: "/auth" });

/** Lỗi -> câu hiển thị (kèm gợi ý TOTP nếu cần). */
export const errText = (e) => (e && e.message) || "Có lỗi không xác định.";
export const isUnavailable = (e) => !!e && (e.code === "unavailable");

/** Dựng thân sự kiện tải tệp từ văn bản (CSV có BOM để Excel đọc tiếng Việt). Không lưu vào storage. */
export function downloadText(filename, text, mime = "text/csv;charset=utf-8") {
  const blob = new Blob(["﻿", text], { type: mime });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}
export const csvCell = (v) => { const s = v == null ? "" : String(v); return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
/** Chống CSV injection khi mở bằng Excel: ô bắt đầu bằng = + - @ được thêm dấu nháy đơn. */
export const csvSafe = (v) => { const s = v == null ? "" : String(v); return /^[=+\-@\t\r]/.test(s) ? `'${s}` : s; };
