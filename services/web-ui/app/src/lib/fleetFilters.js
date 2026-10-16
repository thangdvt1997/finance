// Bộ lọc danh sách đội tài khoản nằm trong địa chỉ (#/doi-tai-khoan?group=..&ea=offline) -> chia sẻ được, nút Quay lại giữ nguyên trạng thái.
import { useCallback, useEffect, useState } from "react";
import { readHashQuery, setHashQuery } from "../ux/urlstate";

export const FILTER_KEYS = ["q", "group", "tag", "status", "ea", "compliance", "incident"];
const ALL = [...FILTER_KEYS, "sort", "dir", "page", "acc"];

const read = () => { const p = readHashQuery(); return Object.fromEntries(ALL.map((k) => [k, p.get(k) || ""])); };

export function useFleetFilters() {
  const [v, setV] = useState(read);
  useEffect(() => {
    const h = () => setV(read());
    addEventListener("hashchange", h); addEventListener("ts-hashq", h);
    return () => { removeEventListener("hashchange", h); removeEventListener("ts-hashq", h); };
  }, []);
  /** patch: {khoá: giá trị|""}. Đổi bộ lọc => về trang 1. */
  const set = useCallback((patch) => {
    const touchesFilter = Object.keys(patch).some((k) => FILTER_KEYS.includes(k));
    setHashQuery({ ...patch, ...(touchesFilter && !("page" in patch) ? { page: "" } : {}) });
  }, []);
  const clear = useCallback(() => setHashQuery(Object.fromEntries([...FILTER_KEYS, "page"].map((k) => [k, ""]))), []);
  const filters = Object.fromEntries(FILTER_KEYS.filter((k) => v[k]).map((k) => [k, v[k]]));
  return { v, set, clear, filters, active: Object.keys(filters).length };
}
