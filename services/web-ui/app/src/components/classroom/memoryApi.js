// Lớp API "Bộ nhớ của AI" (hợp đồng: docs/handoff/MEMORY_API.md). Chỉ nghiên cứu/paper.
import { api, apiWrite } from "../../lib/api";

const B = "/ai-trading/class";
export const mget = (path, params, signal) => api(`${B}${path}`, params || {}, signal);
export const mw = (method, path, body) => apiWrite(method, `${B}${path}`, method === "DELETE" ? undefined : (body ?? {}), { maxBytes: 900_000 });

export const TYPES = {
  knowledge: ["Tri thức phương pháp", "Method knowledge"], lesson: ["Bài học / sửa sai", "Lesson / correction"], label: ["Nhãn ví dụ", "Example label"],
  test_result: ["Kết quả test", "Test result"], preference: ["Sở thích chuyên gia", "Expert preference"], term: ["Thuật ngữ cá nhân", "Personal term"],
};
export const STATUS = {
  proposed: ["Đề xuất", "Proposed", ""], confirmed: ["Đã xác nhận", "Confirmed", "up"], rejected: ["Bị bác", "Rejected", "down"], revoked: ["Thu hồi", "Revoked", "down"],
};
export const TOPICS = {
  context: ["Bối cảnh", "Context"], symbol_tf: ["Mã & khung", "Symbol & timeframe"], formation: ["Hình thành", "Formation"], trigger: ["Kích hoạt", "Trigger"],
  invalidation: ["Điều kiện huỷ", "Invalidation"], sl: ["SL", "Stop loss"], tp: ["TP", "Take profit"], sizing: ["Khối lượng", "Sizing"], filters: ["Bộ lọc", "Filters"],
  ex_ok: ["Ví dụ đúng", "Good examples"], ex_bad: ["Ví dụ sai", "Bad examples"], failure: ["Thất bại", "Failure"], symmetry: ["Đối xứng", "Symmetry"],
  rationale: ["Lý do", "Rationale"], assumptions: ["Giả định", "Assumptions"], general: ["Chung", "General"],
};
export const EVENTS = {
  create: ["Tạo", "Created"], extract: ["AI trích", "Extracted"], merge: ["Hợp nhất", "Merged"], confirm: ["Xác nhận", "Confirmed"], reject: ["Bác", "Rejected"], edit: ["Sửa", "Edited"],
  pin: ["Ghim", "Pin"], lock: ["Khoá", "Lock"], revoke: ["Thu hồi", "Revoked"], delete: ["Xoá", "Deleted"], conflict: ["Mâu thuẫn", "Conflict"], resolve: ["Giải quyết", "Resolved"],
  import: ["Nhập", "Imported"], decay: ["Giảm trọng số", "Decayed"],
};
export const REASONS = {
  injection: ["bị chặn: giống chỉ thị cho AI", "blocked: looks like an instruction to the AI"], secret: ["bị chặn: giống khoá/mật khẩu", "blocked: looks like a key/password"],
  pii: ["bị chặn: thông tin cá nhân", "blocked: personal data"], account: ["bị chặn: thông tin tài khoản", "blocked: account info"],
  promise: ["bị chặn: lời hứa lợi nhuận", "blocked: profit promise"], empty: ["trống", "empty"], too_long: ["quá dài", "too long"],
};
export const lab = (map, k, en) => (map[k] ? map[k][en ? 1 : 0] : k);
export const errText = (e, en) => { const r = e?.detail && typeof e.detail === "object" ? e.detail.reason : null; return r && REASONS[r] ? `${e.message} (${REASONS[r][en ? 1 : 0]})` : e?.message || ""; };

/** Tải JSON về máy (xuất bộ nhớ). */
export function saveJson(name, obj) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" }));
  const a = document.createElement("a"); a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
