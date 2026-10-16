// Trạng thái trong địa chỉ (deep link): phần sau "?" của hash, ví dụ #/tro-giup?tab=thuat-ngu&term=spread. Không đụng phần đường dẫn.
import { useCallback, useEffect, useState } from "react";

export function readHashQuery() {
  const h = location.hash, i = h.indexOf("?");
  return new URLSearchParams(i < 0 ? "" : h.slice(i + 1));
}
/** Ghi thay đổi vào hash (replaceState: không thêm mục lịch sử). patch: {khoá: giá trị | null}. */
export function setHashQuery(patch) {
  const h = location.hash || "#/", i = h.indexOf("?");
  const base = i < 0 ? h : h.slice(0, i);
  const p = readHashQuery();
  for (const [k, v] of Object.entries(patch)) { if (v == null || v === "") p.delete(k); else p.set(k, String(v)); }
  const qs = p.toString();
  history.replaceState(null, "", `${base}${qs ? `?${qs}` : ""}`);
  dispatchEvent(new Event("ts-hashq"));
}
/** [giá trị, đặt] gắn với một khoá trong hash. */
export function useHashQuery(key, def = "") {
  const [v, setV] = useState(() => readHashQuery().get(key) ?? def);
  useEffect(() => {
    const h = () => setV(readHashQuery().get(key) ?? def);
    addEventListener("hashchange", h); addEventListener("ts-hashq", h);
    return () => { removeEventListener("hashchange", h); removeEventListener("ts-hashq", h); };
  }, [key, def]);
  const set = useCallback((nv) => { setV(nv ?? def); setHashQuery({ [key]: nv === def ? null : nv }); }, [key, def]);
  return [v, set];
}
