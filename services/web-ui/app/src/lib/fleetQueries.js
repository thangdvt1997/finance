// Hook dữ liệu + quyền cho các trang quản trị đội tài khoản. Mọi truy vấn tạm dừng khi tab ẩn (refetchIntervalInBackground=false mặc định).
import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { fetchMe } from "./clientsApi";
import { fget, fpost, fput, fpatch, fdel, useViewAsGrant } from "./fleetApi";

/** Cùng khoá ["me"] với App.jsx -> dùng chung bộ nhớ đệm. Gồm role, perms[], scope, totp_enabled, totp_setup_required. */
export const useAuthMe = () => useQuery({ queryKey: ["me"], queryFn: fetchMe, staleTime: 300_000, retry: false });

export const PERM_VN = {
  "fleet.read": "xem đội tài khoản", "incident.read": "xem sự cố", "incident.note": "ghi chú sự cố", "note.write": "ghi chú khách hàng",
  "compliance.read": "xem tuân thủ luật", "report.read": "xem báo cáo", "audit.read": "xem nhật ký kiểm toán",
};
export const ROLE_VN = { master: "Master", support: "Hỗ trợ", analyst: "Phân tích", auditor: "Kiểm toán", client: "Khách hàng" };

/**
 * Quyền hiện tại. `has(perm)` = vai trò có quyền ĐỌC/dùng (master luôn có). `reason(perm, {master})` = lý do khoá nút ghi (null = được phép).
 * `write(perm,{master})` = true nếu được ghi: không đang xem-như-khách + đủ quyền (+ phải là master nếu master:true). KHÔNG thay thế kiểm tra phía máy chủ.
 */
export function usePerm() {
  const me = useAuthMe();
  const grant = useViewAsGrant();
  const d = me.data;
  const role = d?.role || "master";
  const isMaster = role === "master";
  const perms = d?.perms || [];
  return useMemo(() => {
    const has = (p) => !p || isMaster || perms.includes("*") || perms.includes(p);
    const reason = (p, o = {}) => {
      if (grant) return "Đang xem như khách: thao tác ghi bị khoá.";
      if (o.master && !isMaster) return "Chỉ master mới được thực hiện thao tác này.";
      if (!has(p)) return `Vai trò ${ROLE_VN[role] || role} không có quyền ${PERM_VN[p] || p}.`;
      return null;
    };
    return { me: d, role, isMaster, perms, has, reason, write: (p, o) => reason(p, o) === null, viewAs: grant, loading: me.isPending, totpRequired: !!d?.totp_setup_required };
  }, [d, role, isMaster, perms, grant, me.isPending]);
}

// ---------- đọc ----------
const GET = (key, path, params, opt = {}) => ({ queryKey: ["fl", key, params || {}], queryFn: ({ signal }) => fget(path, params, { signal }), retry: false, staleTime: 10_000, ...opt });

export const useFleetList = (params, opt) => useQuery(GET("fleet", "/fleet", params, { refetchInterval: 20_000, placeholderData: keepPreviousData, ...opt }));
export const useGroups = (opt) => useQuery(GET("groups", "/groups", null, { staleTime: 30_000, ...opt }));
export const useTags = (opt) => useQuery(GET("tags", "/tags", null, { staleTime: 30_000, ...opt }));
export const useViews = (opt) => useQuery(GET("views", "/views", null, { staleTime: 30_000, ...opt }));
export const useGroupPolicy = (id) => useQuery(GET("policy", `/groups/${id}/policy`, { id }, { enabled: !!id }));
export const useAccountNotes = (id) => useQuery(GET("notes", `/accounts/${encodeURIComponent(id)}/notes`, { id }, { enabled: !!id }));
export const useAssignees = (opt) => useQuery(GET("assignees", "/incidents/assignees", null, { staleTime: 60_000, ...opt }));
export const useIncidentCounts = (enabled = true) => useQuery({
  queryKey: ["fl", "inc-counts"], enabled, retry: false, staleTime: 20_000, refetchInterval: 45_000,
  queryFn: ({ signal }) => fget("/incidents", { status: "active", limit: 1 }, { signal }).then((r) => r.counts || {}),
});
export const useCompliance = (params, opt) => useQuery(GET("compliance", "/compliance", params, { refetchInterval: 30_000, placeholderData: keepPreviousData, ...opt }));
export const useRulePresets = (opt) => useQuery(GET("presets", "/rules/presets", null, { staleTime: 300_000, ...opt }));
export const useRuleTemplates = (opt) => useQuery(GET("tpl", "/rules/templates", null, opt));
export const useRuleAssignments = (opt) => useQuery(GET("assign", "/rules/assignments", null, opt));
export const useRoles = (opt) => useQuery(GET("roles", "/roles", null, { staleTime: 120_000, ...opt }));
export const useStaff = (opt) => useQuery(GET("staff", "/staff", null, opt));
export const useViewAsActive = (opt) => useQuery(GET("va-active", "/view-as/active", null, { staleTime: 5_000, ...opt }));

/** Nhật ký kiểm toán theo đối tượng (tài khoản/nhóm...). Có `before_id` để tải thêm. */
export const useAuditTarget = (target, limit = 100) => useQuery(GET("audit", "/audit", { target, limit }, { enabled: !!target, staleTime: 10_000 }));

// ---------- ghi ----------
/** useMutation gọn: fn(vars) -> Promise; sau khi xong làm mới các khoá ["fl", ...inv]. */
export function useFleetMut(fn, inv = [], opt = {}) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    ...opt,
    onSuccess: (...a) => { for (const k of inv) qc.invalidateQueries({ queryKey: ["fl", k] }); opt.onSuccess?.(...a); },
  });
}
export const api = { get: fget, post: fpost, put: fput, patch: fpatch, del: fdel };

// ---------- nhãn dùng chung ----------
export const EA_VN = { online: "Trực tuyến", degraded: "Chập chờn", offline: "Mất kết nối", unknown: "Chưa kết nối" };
export const ACC_STATUS_VN = { active: "Hoạt động", pending: "Chờ duyệt", suspended: "Đình chỉ" };
export const COMP_VN = { green: "Trong hạn mức", yellow: "Sát ngưỡng", red: "Vi phạm", na: "Chưa có dữ liệu" };
export const SEV_VN = { info: "Thông tin", warning: "Cảnh báo", critical: "Nghiêm trọng" };
export const INC_STATUS_VN = { open: "Mới", ack: "Đã nhận", snoozed: "Tạm hoãn", resolved: "Đã đóng" };
export const KIND_VN = { daily_loss: "Lỗ trong ngày", max_drawdown: "Drawdown tối đa", margin_level: "Margin level tối thiểu", best_day: "Ngày lãi tốt nhất", max_trades_day: "Số lệnh mỗi ngày" };
