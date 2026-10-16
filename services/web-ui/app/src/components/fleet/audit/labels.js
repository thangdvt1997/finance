// Nhãn hành động nhật ký kiểm toán: nhãn cũ (clientsQueries.AUDIT_VN) + hành động của quản trị đội tài khoản (services/auth/src/auth/fleet*.py).
import { AUDIT_VN } from "../../../lib/clientsQueries";

export const AUDIT_FLEET_VN = {
  account_groups_set: "Đặt nhóm cho tài khoản", account_tags_set: "Đặt tag cho tài khoản", account_note_added: "Thêm ghi chú tài khoản",
  group_created: "Tạo nhóm", group_updated: "Sửa nhóm", group_deleted: "Xoá nhóm", group_members_added: "Thêm tài khoản vào nhóm", group_member_removed: "Gỡ tài khoản khỏi nhóm", group_policy_changed: "Đổi chính sách nhóm",
  bulk_prepared: "Chuẩn bị thao tác hàng loạt", bulk_executed: "Thực hiện thao tác hàng loạt",
  import_previewed: "Xem trước nhập CSV", import_committed: "Nhập CSV tài khoản",
  rule_template_created: "Tạo mẫu luật", rule_template_updated: "Sửa mẫu luật", rule_template_deleted: "Xoá mẫu luật",
  rule_assigned: "Gán luật", rule_assignment_updated: "Sửa gán luật", rule_assignment_deleted: "Gỡ gán luật",
  incident_ack: "Nhận sự cố", incident_reopen: "Mở lại sự cố", incident_assign: "Giao sự cố", incident_snooze: "Tạm hoãn sự cố", incident_resolve: "Đóng sự cố", incident_notes: "Ghi chú sự cố", incident_note: "Ghi chú sự cố", incident_bulk: "Xử lý sự cố hàng loạt",
  staff_created: "Tạo nhân sự", staff_updated: "Sửa nhân sự", view_as_end: "Kết thúc xem như khách",
  totp_setup: "Khởi tạo TOTP", client_notify_set: "Khách đổi thông báo", view_created: "Lưu bộ lọc",
  ea_paired: "EA ghép cặp", ea_pair_fail: "EA ghép cặp sai", ea_credentials_delivered: "Giao thông tin EA", ea_self_registered: "EA tự đăng ký",
};
export const AUDIT_ALL_VN = { ...AUDIT_VN, ...AUDIT_FLEET_VN };
export const actionLabel = (a) => AUDIT_ALL_VN[a] || (a || "").replace(/_/g, " ");
export const actionOptions = () => Object.entries(AUDIT_ALL_VN).sort((a, b) => a[1].localeCompare(b[1], "vi"));

// Hành động cần chú ý (nền đỏ/vàng): dùng cùng biểu tượng + chữ ở UI, không chỉ màu.
const BAD = /(_fail|locked|blocked|deleted|bad_)/;
const WARN = /(suspend|rotated|reset|revoked|view_as|bulk_executed|import_committed|staff_|totp_disabled|logout_all)/;
export const actionTone = (a) => (BAD.test(a || "") ? "bad" : WARN.test(a || "") ? "warn" : "mute");

// Không bao giờ hiển thị bí mật trong chi tiết.
const SECRET = /secret|password|passcode|token|hmac|pairing_code|totp_secret|hash|cookie|authorization/i;
export function redact(v, depth = 0) {
  if (v == null || typeof v !== "object") return v;
  if (depth > 4) return "…";
  if (Array.isArray(v)) return v.slice(0, 50).map((x) => redact(x, depth + 1));
  const o = {};
  for (const [k, x] of Object.entries(v)) o[k] = SECRET.test(k) ? "••• (ẩn)" : redact(x, depth + 1);
  return o;
}
export const detailText = (d) => { try { return JSON.stringify(redact(d)); } catch { return ""; } };
