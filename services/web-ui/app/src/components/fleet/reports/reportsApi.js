// Lớp dữ liệu "Báo cáo khách" (docs/FLEET_MGMT.md mục 5). Đọc: api(); ghi: apiWrite() (CSRF tự động). Chỉ-đọc về giao dịch — không có đường đặt lệnh.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiWrite, ApiError } from "../../../lib/api";

export const KIND_VN = { daily: "Ngày", weekly: "Tuần", monthly: "Tháng" };
export const KINDS = ["daily", "weekly", "monthly"];
export const ACC_RE = /^[A-Za-z0-9_.:-]{1,64}$/;

/** Chuẩn hoá lỗi: route chưa có / nginx chưa mở -> code "unavailable" (UI hiện Unavailable thay vì lỗi đỏ). */
export function norm(e) {
  if (e?.name === "AbortError") return e;
  const status = e instanceof ApiError ? e.status : 404; // thân không phải JSON (nginx trả trang SPA) = route chưa mở
  const code = status === 0 ? "network" : [404, 405, 502, 503].includes(status) ? "unavailable" : status === 403 ? "forbidden" : "";
  const err = new Error(e?.message && e instanceof ApiError ? e.message : "Máy chủ chưa hỗ trợ mục này.");
  err.status = status; err.code = code; err.detail = e?.detail;
  return err;
}
async function rd(path, params, signal) { try { return await api(path, params, signal); } catch (e) { throw norm(e); } }
async function wr(method, path, body) { try { return await apiWrite(method, path, body); } catch (e) { throw norm(e); } }

const arr = (d) => (Array.isArray(d) ? d : Array.isArray(d?.items) ? d.items : Array.isArray(d?.reports) ? d.reports : []);
const KEY = ["fl", "acc-reports"];

export const useReports = (accountId) => useQuery({
  queryKey: [...KEY, accountId || ""], enabled: !!accountId, retry: false, staleTime: 15_000,
  refetchInterval: (q) => (q.state.error ? 30_000 : 60_000),
  queryFn: async ({ signal }) => arr(await rd("/account-reports", { account_id: accountId }, signal)),
});
export const useSchedules = (enabled) => useQuery({
  queryKey: ["fl", "acc-sched"], enabled, retry: false, staleTime: 15_000,
  refetchInterval: (q) => (q.state.error ? 30_000 : 90_000),
  queryFn: async ({ signal }) => { const d = await rd("/account-report-schedules", {}, signal); return Array.isArray(d) ? d : Array.isArray(d?.schedules) ? d.schedules : arr(d); },
});

export function useReportMut() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: KEY });
  return {
    generate: (v) => wr("POST", "/account-reports/generate", v).then((r) => { done(); return r; }),
    release: useMutation({ mutationFn: (v) => wr("POST", "/account-reports/release", v), onSuccess: done }),
    refresh: done,
  };
}
export function useScheduleMut() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (schedules) => wr("PUT", "/account-report-schedules", { schedules }), onSuccess: () => qc.invalidateQueries({ queryKey: ["fl", "acc-sched"] }) });
}

/** Đường dẫn xem HTML/PDF (mở tab mới; iframe bị CSP chặn). */
export const fileHref = (it, ext) => `/api/v1/account-reports/${it.account_id}/${it.period}/${ext}?kind=${encodeURIComponent(it.kind)}`;
export const dmy = (p) => (/^\d{4}-\d{2}-\d{2}$/.test(p || "") ? p.split("-").reverse().join("/") : p || "—");
export const kb = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round((n || 0) / 1024))} KB`);
