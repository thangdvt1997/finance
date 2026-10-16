// MOCK cho GET/PUT /user/client-prefs (chế độ ?mock=1). Lưu trong localStorage của trình duyệt (giả lập "máy chủ").
// Cờ thử: &mockprefs=404 (backend chưa có) · &mockprefs=409 (lần PUT đầu bị 409 rồi mới được) · &mockprefs=off (xoá cờ).
import { ApiError } from "./api";

const K = "tc-mock-prefs", FLAG = "tc-mock-prefs-mode";
const mode = () => {
  try {
    const q = new URLSearchParams(location.search + (location.hash.includes("?") ? "&" + location.hash.split("?")[1] : ""));
    const m = q.get("mockprefs");
    if (m === "off") { sessionStorage.removeItem(FLAG); sessionStorage.removeItem(FLAG + "-409done"); } else if (m) sessionStorage.setItem(FLAG, m);
    return sessionStorage.getItem(FLAG) || "";
  } catch { return ""; }
};
// khởi tạo: có sẵn cài đặt thông báo (khoá notif) như máy chủ thật; KHÔNG có lang/theme (thiết bị chưa từng đồng bộ)
const SEED = { rev: 3, data: { notif: { rule: { app: true, push: true }, limit: { app: true, push: true }, report: { app: true, push: false }, briefing: { app: true, push: false }, support: { app: true, push: true } } } };
const read = () => { try { return JSON.parse(localStorage.getItem(K)) || SEED; } catch { return SEED; } };

/** Trả undefined nếu không xử lý. */
export async function handlePrefs(method, path, body) {
  if (path !== "/user/client-prefs") return undefined;
  const m = mode();
  if (m === "404") throw new ApiError(404, "Không tìm thấy (hoặc máy chủ chưa hỗ trợ).", "not_found");
  const cur = read();
  if (method === "GET") return cur;
  if (method === "PUT") {
    if (m === "409" && !sessionStorage.getItem(FLAG + "-409done")) {
      sessionStorage.setItem(FLAG + "-409done", "1"); // chỉ một lần cho mỗi phiên trình duyệt
      // giả lập thiết bị khác vừa ghi: tăng rev và đổi một khoá
      const other = { rev: cur.rev + 1, data: { ...cur.data, density: "compact" } };
      localStorage.setItem(K, JSON.stringify(other));
      throw new ApiError(409, "Dữ liệu đã thay đổi ở nơi khác.", "rev_conflict");
    }
    if (Number(body?.rev) !== cur.rev) throw new ApiError(409, "Dữ liệu đã thay đổi ở nơi khác.", "rev_conflict");
    const next = { rev: cur.rev + 1, data: body?.data && typeof body.data === "object" ? body.data : {} };
    localStorage.setItem(K, JSON.stringify(next));
    return next;
  }
  return undefined;
}
