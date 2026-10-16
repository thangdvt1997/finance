// Thông tin thị trường tổng hợp (api-gateway /v1/intel/*): hooks + tiện ích dùng chung cho các trang/widget "intel".
// Mọi số là thống kê từ dữ liệu giá/tin đã lưu, không phải khuyến nghị. Không hiển thị tên nguồn dữ liệu.
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { api } from "./api";
import "../intel.css";

const q = (key, path, params, opts = {}) => ({
  queryKey: ["intel", key, params],
  queryFn: ({ signal }) => api(path, params, signal),
  staleTime: 15_000,
  placeholderData: keepPreviousData,
  ...opts,
});

export const useStrength = (tf = "D1", window) => useQuery(q("strength", "/intel/strength", { tf, window }, { refetchInterval: 30_000 }));
export const useFxMatrix = () => useQuery(q("fx", "/intel/fx", {}, { refetchInterval: 30_000 }));
export const useHeatmap = (group = "crypto", period = "1d") => useQuery(q("heatmap", "/intel/heatmap", { group, period }, { refetchInterval: 45_000 }));
export const useMovers = (group = "all", period = "1d", limit = 10, pollMs = 45_000) => useQuery(q("movers", "/intel/movers", { group, period, limit }, { refetchInterval: (qy) => (qy.state.status === "error" ? false : pollMs), refetchIntervalInBackground: false }));
export const useIntelStats = (group = "all", benchmark = "US:SPY", window = 60) =>
  useQuery(q("stats", "/intel/stats", { group, benchmark, window }, { refetchInterval: 120_000, staleTime: 60_000 }));
export const useCorrelationMatrix = (symbols, window = 60, method = "pearson") =>
  useQuery(q("corr", "/intel/correlation", { symbols: (symbols || []).join(",") || undefined, window, method }, { staleTime: 60_000, refetchInterval: 300_000 }));
export const useRollingCorr = (a, b, window = 30, span = 250) =>
  useQuery(q("rolling", "/intel/correlation/rolling", { a, b, window, span }, { enabled: !!a && !!b && a !== b, staleTime: 60_000, retry: false }));
export const useDistribution = (symbol, window = 250) =>
  useQuery(q("dist", "/intel/distribution", { symbol, window }, { enabled: !!symbol, staleTime: 60_000, retry: false }));
export const usePulse = () => useQuery(q("pulse", "/intel/pulse", {}, { refetchInterval: 60_000, staleTime: 30_000 }));
export const useNewsTopics = (hours = 24) => useQuery(q("ntopics", "/intel/news/topics", { hours }, { refetchInterval: 60_000 }));
export const useNewsRelated = (url) => useQuery(q("nrelated", "/intel/news/related", { url }, { enabled: !!url, retry: false, staleTime: 120_000 }));
export const useCalIndicators = () => useQuery(q("calind", "/intel/calendar/indicators", {}, { staleTime: 300_000 }));
export const useCalHistory = (title, country) =>
  useQuery(q("calhist", "/intel/calendar/history", { title, country, limit: 40 }, { enabled: !!title, retry: false, staleTime: 120_000 }));
export const useCot = () => useQuery(q("cot", "/intel/cot", {}, { refetchInterval: 600_000, staleTime: 300_000 }));
/** Truy vấn tin 1 trang (không phân trang vô hạn): dùng cho widget. */
export const useIntelNews = (params, opts = {}) => useQuery(q("news", "/intel/news", params, { refetchInterval: 45_000, ...opts }));

export const ASSET_GROUPS = [
  { value: "crypto", label: "Tiền ảo" },
  { value: "etf", label: "Chỉ số & ETF toàn cầu" },
  { value: "sector", label: "Ngành Mỹ (ETF)" },
  { value: "commodity", label: "Kim loại & hàng hoá" },
  { value: "forex", label: "Forex" },
  { value: "us_stock", label: "Cổ phiếu Mỹ" },
  { value: "bond", label: "Trái phiếu" },
  { value: "vn", label: "Cổ phiếu VN" },
];
export const PERIOD_LABEL = { "1h": "1 giờ", "4h": "4 giờ", "1d": "1 ngày", "1w": "1 tuần", "1m": "1 tháng", "3m": "3 tháng", "6m": "6 tháng", ytd: "Từ đầu năm", "1y": "1 năm" };

// ---------------------------------------------------------------- định dạng
export const fpct = (v, dp = 2) => (v == null || Number.isNaN(v) ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(dp)}%`);
export const fnum = (v, dp = 2) => (v == null || Number.isNaN(v) ? "—" : Number(v).toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp }));
export const fcompact = (v) => {
  if (v == null || Number.isNaN(v)) return "—";
  const a = Math.abs(v);
  const s = a >= 1e12 ? `${(a / 1e12).toFixed(2)}T` : a >= 1e9 ? `${(a / 1e9).toFixed(2)}B` : a >= 1e6 ? `${(a / 1e6).toFixed(2)}M` : a >= 1e3 ? `${(a / 1e3).toFixed(1)}K` : a.toFixed(a < 10 ? 2 : 0);
  return v < 0 ? `−${s}` : s;
};
/** Giá hiển thị gọn theo độ lớn (không biết số lẻ chuẩn của từng mã). */
export const fprice = (v) => {
  if (v == null || Number.isNaN(v)) return "—";
  const a = Math.abs(v);
  const dp = a >= 10 ? 2 : a >= 1 ? 4 : a >= 0.01 ? 5 : 8;
  return Number(v).toLocaleString("en-US", { minimumFractionDigits: Math.min(dp, 2), maximumFractionDigits: dp });
};
export const signCls = (v) => (v > 0 ? "up" : v < 0 ? "down" : "flat");
/** Liên kết mở biểu đồ của mã. */
export const chartHref = (symbol) => `#/thi-truong/${encodeURIComponent(symbol)}`;

/** Lớp màu heat theo % (xanh tăng/đỏ giảm, 5 bậc). cap = % bão hoà. */
export function heatClass(p, cap = 3) {
  if (p == null || Number.isNaN(p)) return "h-na";
  const t = Math.min(Math.abs(p) / cap, 1);
  const b = t < 0.06 ? 0 : t < 0.25 ? 1 : t < 0.5 ? 2 : t < 0.78 ? 3 : 4;
  return b === 0 ? "h-0" : `${p > 0 ? "hu" : "hd"}-${b}`;
}
/** Màu liên tục cho biểu đồ (CSS color-mix) theo giá trị -1..1 */
export const mixColor = (t, pos = "var(--up)", neg = "var(--down)") => {
  const a = Math.min(1, Math.abs(t));
  return `color-mix(in srgb, ${t >= 0 ? pos : neg} ${Math.round(14 + 76 * a)}%, var(--panel2))`;
};
export const CCY_NAME = { USD: "Đô la Mỹ", EUR: "Euro", GBP: "Bảng Anh", JPY: "Yên Nhật", CHF: "Franc Thụy Sĩ", CAD: "Đô la Canada", AUD: "Đô la Úc", NZD: "Đô la New Zealand" };
export const CCY_COLOR = { USD: "#5aa9ff", EUR: "#f0b84f", GBP: "#c58bff", JPY: "#ff7a90", CHF: "#7be0c3", CAD: "#ff9f5a", AUD: "#6fd16f", NZD: "#9fb4cc" };
/** Màu chữ cho tiền tệ: tối đi ở giao diện sáng (--ccy-dark) để đạt tương phản AA; biểu đồ vẫn dùng CCY_COLOR gốc. */
export const ccyInk = (c) => `color-mix(in srgb, ${CCY_COLOR[c] || "currentColor"}, #000 var(--ccy-dark, 0%))`;
