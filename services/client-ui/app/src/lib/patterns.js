// Kịch bản Sell (KB-1..KB-4): tín hiệu CHUNG (không theo tài khoản), kết quả PAPER. Gateway /v1/patterns/* đã lọc cho client
// (chỉ armed/triggered, không lý do huỷ, không tham số). Hợp đồng: docs/handoff/SCAN_status.md.
// Dữ liệu mẫu: ?mock=1 (chế độ mẫu chung) hoặc ?mockpat=1 (chỉ mục này; nhớ trong sessionStorage, ?mockpat=0 tắt).
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { api, MOCK } from "./api";

const FLAG = "tc-mockpat";
function mockOn() {
  if (MOCK) return true;
  try {
    const p = new URLSearchParams(location.search + (location.hash.includes("?") ? "&" + location.hash.split("?")[1] : ""));
    if (p.get("mockpat") === "1") sessionStorage.setItem(FLAG, "1");
    if (p.get("mockpat") === "0") sessionStorage.removeItem(FLAG);
    return sessionStorage.getItem(FLAG) === "1";
  } catch { return false; }
}
export const PAT_MOCK = mockOn();
const get = async (path, params, signal) => (PAT_MOCK ? (await import("./patternsFixture.js")).handle(path, params) : api(path, params, signal));
const q = (key, path, params, opts = {}) => ({
  queryKey: ["pat", key, params], queryFn: ({ signal }) => get(path, params, signal), staleTime: 15_000,
  placeholderData: keepPreviousData, retry: (n, e) => n < 1 && !(e?.status >= 400 && e.status < 500), ...opts,
});

export const usePatLive = (p) => useQuery(q("live", "/patterns/live", p, { refetchInterval: 30_000 }));
export const usePatSetup = (p) => useQuery(q("setup", "/patterns/setup", p, { enabled: !!p?.setup_id, refetchInterval: 30_000 }));
export const usePatTrades = (p) => useQuery(q("trades", "/patterns/trades", p, { refetchInterval: 60_000 }));
export const usePatStats = () => useQuery(q("stats", "/patterns/stats", {}, { refetchInterval: 60_000 }));
export const usePatExamples = () => useQuery(q("examples", "/patterns/examples", {}, { staleTime: 300_000 }));
export const usePatSpec = () => useQuery(q("spec", "/patterns/spec", {}, { staleTime: 600_000 }));
/** Nến quanh một setup (khi setup không kèm `bars`). */
export const usePatBars = (symbol, tf, win, enabled) =>
  useQuery(q("bars", "/bars", { symbol, tf, from: win?.from, to: win?.to, order: "desc", limit: 400 }, { enabled: !!(enabled && symbol && tf), staleTime: 60_000 }));
/** /patterns/setup trả {item, marks, window, disclaimer} (bản cũ: chính item) -> chuẩn hoá. */
export const setupOf = (d) => (d?.item ? { s: d.item, marks: d.marks || d.item.marks || [], win: d.window || null } : d?.setup_id ? { s: d, marks: d.marks || [], win: null } : null);

/** Ảnh: máy chủ trả đường dẫn tương đối "/v1/patterns/media/<id>.png" -> ghép với base API của client ("/c/api"). */
export function imgUrl(p) {
  if (!p || typeof p !== "string") return null;
  if (p.startsWith("data:image/")) return p; // chỉ dữ liệu mẫu
  if (p.startsWith("/v1/patterns/")) return `/c/api${p}`;
  if (p.startsWith("/c/api/v1/patterns/")) return p;
  return null; // không nhận URL ngoài
}

/** Danh sách item từ phản hồi ({items:[..]} | [..]). */
export const itemsOf = (d) => (Array.isArray(d) ? d : Array.isArray(d?.items) ? d.items : []);
export const TF_SEC = { M1: 60, M5: 300, M15: 900, M30: 1800, H1: 3600, H4: 14400, D1: 86400 };
