import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { api } from "./api";

// Chứng khoán Việt Nam cuối ngày (api-gateway /v1/vn/* -> service vn-market). Chỉ-đọc. Nguồn VNDirect finfo, KHÔNG realtime.
const q = (key, path, params, opts = {}) => ({
  queryKey: ["vn", key, params],
  queryFn: ({ signal }) => api(`/vn${path}`, params, signal),
  staleTime: 60_000,
  refetchInterval: 300_000,
  placeholderData: keepPreviousData,
  ...opts,
});
export const useVnOverview = () => useQuery(q("overview", "/overview", {}));
export const useVnStatus = () => useQuery(q("status", "/status", {}, { staleTime: 120_000 }));
export const useVnHeatmap = (p) => useQuery(q("heatmap", "/heatmap", p));
export const useVnMovers = (p) => useQuery(q("movers", "/movers", p));
export const useVnLimits = (p) => useQuery(q("limits", "/limits", p));
export const useVnForeign = (p) => useQuery(q("foreign", "/foreign", p));
export const useVnScreener = (p) => useQuery(q("screener", "/screener", p));
export const useVnEvents = (p) => useQuery(q("events", "/events", p));
export const useVnNews = (p) => useQuery(q("news", "/news", p));
export const useVnLiquidity = (p) => useQuery(q("liq", "/liquidity", p));
export const useVnSymbol = (code) => useQuery(q(`sym-${code}`, `/symbol/${encodeURIComponent(code || "")}`, { n: 500 }, { enabled: !!code, retry: false }));
export const useVnSymbols = (p) => useQuery(q("symbols", "/symbols", p, { staleTime: 600_000 }));

const nf0 = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("vi-VN", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat("vi-VN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const n0 = (v) => (v == null ? "—" : nf0.format(v));
export const n1 = (v) => (v == null ? "—" : nf1.format(v));
export const n2 = (v) => (v == null ? "—" : nf2.format(v));
/** Giá VND: số nguyên có dấu chấm nghìn (57.700). */
export const vnd = (v) => (v == null ? "—" : nf0.format(Math.round(v)));
/** Giá trị tiền: tỷ / nghìn tỷ (đồng). */
export function bil(v, signed = false) {
  if (v == null) return "—";
  const a = Math.abs(v), s = signed && v > 0 ? "+" : v < 0 ? "−" : "";
  if (a >= 1e12) return `${s}${nf1.format(a / 1e12)} nghìn tỷ`;
  if (a >= 1e9) return `${s}${a >= 1e11 ? nf0.format(a / 1e9) : nf1.format(a / 1e9)} tỷ`;
  if (a >= 1e6) return `${s}${nf0.format(a / 1e6)} tr`;
  return `${s}${nf0.format(a)}`;
}
export function vol(v) {
  if (v == null) return "—";
  if (v >= 1e6) return `${nf2.format(v / 1e6)} tr`;
  if (v >= 1e3) return `${nf0.format(v / 1e3)} k`;
  return nf0.format(v);
}
export const pc = (v, dp = 2) => (v == null ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(dp).replace(".", ",")}%`);
export const tone = (v) => (v > 0 ? "up" : v < 0 ? "down" : "px-ref");
/** Màu giá theo quy ước bảng điện: trần tím, sàn xanh lơ, tham chiếu vàng, tăng xanh, giảm đỏ. */
export function priceCls(close, basic, ceil, flr) {
  if (close == null) return "flat";
  if (ceil && close >= ceil - 0.5) return "px-ceil";
  if (flr && close <= flr + 0.5) return "px-floor";
  if (basic != null && close > basic) return "up";
  if (basic != null && close < basic) return "down";
  return "px-ref";
}
export const UNIVERSES = [["vn30", "VN30"], ["vn100", "VN100"], ["hose", "HOSE"], ["hnx", "HNX"], ["hnx30", "HNX30"], ["upcom", "UPCoM"], ["etf", "ETF"], ["all", "Tất cả"]];
export const FLOOR_NAME = { HOSE: "HOSE", HNX: "HNX", UPCOM: "UPCoM" };
export const ETYPE = { DIVIDEND: "Cổ tức tiền", STOCKDIV: "Cổ tức cổ phiếu", KINDDIV: "Cổ phiếu thưởng", ISSUE: "Phát hành thêm", MEETING: "Họp ĐHCĐ", meetingRight: "Chốt quyền họp", POLL: "Lấy ý kiến" };
export const goSymbol = (code) => { location.hash = `#/chung-khoan-vn/ma/${code}`; };
