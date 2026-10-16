// Truy vấn + định dạng cho "track record chuyên gia" (gateway /v1/experts/leaderboard|consensus|feed|methodology|{id}/track-record).
// Hợp đồng: services/track-record/CONTRACT.md. Không bao giờ hiển thị khoá nguồn/URL: chỉ dùng nhãn trung lập (clean()).
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { api } from "./api";
import { clean } from "./format";

const FLAG = "ts-mockexp";
function mockOn() {
  try {
    const q = new URLSearchParams(location.search + (location.hash.includes("?") ? "&" + location.hash.split("?")[1] : ""));
    if (q.get("mockexp") === "1") sessionStorage.setItem(FLAG, "1");
    if (q.get("mockexp") === "0") sessionStorage.removeItem(FLAG);
    return sessionStorage.getItem(FLAG) === "1";
  } catch { return false; }
}
async function get(path, params, signal) {
  if (mockOn()) return (await import("./trackrecordFixture.js")).handle(path, params);
  return api(path, params, signal);
}
// 502/503/504 (dịch vụ đang khởi tạo): thử lại có backoff luỹ thừa (2s..30s), tối đa 5 lần; lỗi khác thử 1 lần.
const retry = (n, e) => ([502, 503, 504].includes(e?.status) ? n < 5 : n < 1 && e?.status !== 404);
const retryDelay = (n) => Math.min(30_000, 2000 * 2 ** n);
const q = (key, path, params, opts = {}) => ({ queryKey: ["tr", key, path, params], queryFn: ({ signal }) => get(path, params, signal), retry, retryDelay, staleTime: 30_000, placeholderData: keepPreviousData, ...opts });

export const useLeaderboard = (p) => useQuery(q("lb", "/experts/leaderboard", p, { refetchInterval: 120_000 }));
export const useTrackRecord = (id, p) => useQuery(q("tr", `/experts/${encodeURIComponent(id || "")}/track-record`, p, { enabled: !!id, refetchInterval: 300_000 }));
export const useConsensus = (p) => useQuery(q("cs", "/experts/consensus", p, { refetchInterval: 120_000 }));
export const useFeed = (p) => useQuery(q("fd", "/experts/feed", p, { refetchInterval: 90_000 }));
export const useMethodology = (enabled = true) => useQuery(q("mt", "/experts/methodology", {}, { enabled, staleTime: 3600_000, placeholderData: undefined }));

export const HORIZONS = [["1D", "1 ngày"], ["1W", "1 tuần"], ["1M", "1 tháng"]];
export const HZ_BARS = { "1D": 1, "1W": 5, "1M": 21 };
export const SCOPES = [["all", "Mọi tài sản"], ["forex", "Ngoại hối"], ["metal", "Kim loại"], ["index", "Chỉ số"], ["commodity", "Hàng hoá"], ["crypto", "Tiền số"], ["stock_us", "Cổ phiếu Mỹ"], ["stock_vn", "Cổ phiếu VN"], ["etf", "ETF"], ["bond", "Trái phiếu"]];
export const KINDS = [["", "Mọi loại"], ["analyst", "Chuyên gia phân tích"], ["central_bank", "Ngân hàng trung ương"], ["media", "Luồng tin"], ["positioning", "Vị thế đầu cơ"], ["signal_provider", "Nhà cung cấp tín hiệu"], ["other", "Khác"]];
export const LANGS = [["", "Mọi ngôn ngữ"], ["vi", "Tiếng Việt"], ["en", "Tiếng Anh"], ["other", "Khác"]];
export const REGIMES = { trend: "Xu hướng", range: "Đi ngang", high_vol: "Biến động cao", low_vol: "Biến động thấp" };
export const LEVELS = { none: "Chưa rõ", weak: "Nghiêng nhẹ", consensus: "Đồng thuận" };
export const FIXED_NOTE = "Chỉ tham khảo, quá khứ không đảm bảo tương lai, đa số ý kiến công khai không vượt ngẫu nhiên.";

const lbl = (list, v) => (list.find((x) => x[0] === v) || [v, v])[1];
export const kindLabel = (k) => lbl(KINDS, k || "");
export const langLabel = (l) => lbl(LANGS, l || "");
export const scopeLabel = (s) => (s?.startsWith("sym:") ? s.slice(4).replace(/^[A-Za-z]+:/, "") : lbl(SCOPES, s));
export const labelOf = (s) => clean(String(s ?? ""));

const nf = (n, dp) => Number(n).toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
export const pc = (v, dp = 1) => (v == null || Number.isNaN(v) ? "—" : `${nf(v * 100, dp)}%`);
export const sgn = (v, dp = 2, suf = "%") => (v == null || Number.isNaN(v) ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${nf(Math.abs(v), dp)}${suf}`);
export const qfmt = (v) => (v == null ? "—" : v < 0.01 ? "<0,01" : nf(v, 2).replace(".", ","));
export const wfmt = (v) => (v == null ? "—" : nf(v, 2));
export const dirWord = (d) => (d === "bullish" ? "Tăng" : d === "bearish" ? "Giảm" : d || "—");
export const dirTone = (d) => (d === "bullish" ? "up" : d === "bearish" ? "down" : "");
export const dirArrow = (d) => (d === "bullish" ? "▲" : d === "bearish" ? "▼" : "•");

/** Dòng tóm tắt trung thực dưới bảng xếp hạng. */
export function honestSummary(s) {
  if (!s) return "";
  const parts = [`${s.rated}/${s.entities} chuyên gia đủ mẫu`, `${s.beating_baseline} vượt ngẫu nhiên`];
  const fp = s.expected_false_positives != null ? `kỳ vọng dương tính giả ≈ ${nf(s.expected_false_positives, 1)} (trong ${s.tests} kiểm định, FDR ${nf(s.fdr_q ?? 0.1, 2).replace(".", ",")})` : null;
  return parts.concat(fp ? [fp] : []).join("; ");
}
