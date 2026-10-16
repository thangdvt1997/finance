import { useEffect, useMemo, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { api, TFS } from "./api";
import { seedQuotes } from "./stream";
import { applyTheme, savePref } from "./prefs";
import { useRealtimeLive } from "./useLiveQuote";
import { useRtQuoteFeed } from "./rtbridge";
import { useRtAccounts } from "./rtAccounts";

const q = (key, path, params, opts = {}) => ({
  queryKey: [key, params],
  queryFn: ({ signal }) => api(path, params, signal),
  staleTime: 10_000,
  placeholderData: keepPreviousData,
  ...opts,
});

export const useOverview = () =>
  useQuery({
    ...q("overview", "/overview", {}, { refetchInterval: 30_000 }),
    select: (d) => {
      seedQuotes(d.quotes);
      return d;
    },
  });
export const useQuotesLatest = (symbols) => {
  const live = useRealtimeLive(); // rt đang đẩy giá -> REST chỉ còn là seed/dự phòng (poll thưa)
  useRtQuoteFeed(symbols ? symbols.slice(0, 100) : undefined);
  return useQuery({
    ...q("quotes", "/quotes/latest", { symbols: symbols?.join(",") }, { refetchInterval: live ? 240_000 : 60_000 }),
    select: (d) => {
      seedQuotes(d);
      return d;
    },
  });
};
export const useSymbols = () => useQuery(q("symbols", "/symbols", {}, { staleTime: 60_000, refetchInterval: 120_000 }));
export const useBars = (symbol, tf, limit = 500, opts = {}) =>
  useQuery(q("bars", "/bars", { symbol, tf, limit, order: "desc" }, { enabled: !!symbol && TFS.includes(tf), ...opts }));
export const useNews = (params) => useQuery(q("news", "/news", params, { refetchInterval: 60_000 }));
export const useCalendar = (params, opts) => useQuery(q("calendar", "/calendar", params, { refetchInterval: 120_000, ...opts }));
export const useExperts = () => useQuery(q("experts", "/experts", { limit: 200 }, { refetchInterval: 120_000 }));
export const useSignals = (params) => useQuery(q("signals", "/expert-signals", { limit: 200, ...params }, { refetchInterval: 60_000 }));
export const usePositions = (params) => useQuery(q("xpos", "/expert-positions", { limit: 300, ...params }, { refetchInterval: 120_000 }));
export const useAccounts = () => {
  const live = useRealtimeLive();
  const r = useQuery(q("accounts", "/accounts", {}, { refetchInterval: live ? 120_000 : 15_000 }));
  const ids = useMemo(() => (Array.isArray(r.data) ? r.data.map((a) => a?.account_id).filter(Boolean).sort().join(",") : ""), [r.data]);
  useRtAccounts(live ? ids : "", false); // a:<id> gộp vào cache ["accounts",{}]
  return r;
};
export const useEquity = (account_id, from) =>
  useQuery(q("equity", "/equity-history", { account_id, from, limit: 2000 }, { enabled: !!account_id, refetchInterval: 60_000 }));
export const useAlerts = (params, opts) => useQuery(q("alerts", "/alerts", params, { refetchInterval: 30_000, ...opts }));
// Bộ lọc rủi ro tin (api-gateway /v1/risk-windows): trạng thái cửa sổ T-15..T+30 quanh sự kiện tác động cao
export const useRiskSymbol = (symbol) =>
  useQuery(q(`risk-${symbol}`, "/risk-windows", { symbol }, { enabled: !!symbol, refetchInterval: 30_000, staleTime: 15_000 }));
export const useRiskAll = () => useQuery(q("risk-all", "/risk-windows", {}, { refetchInterval: 30_000, staleTime: 15_000 }));
export const useSystem = () => useQuery(q("system", "/system", {}, { refetchInterval: 10_000, staleTime: 5_000 }));
export const useDataSources = () => useQuery(q("data-sources", "/data-sources", {}, { refetchInterval: 60_000, staleTime: 30_000 }));

// Phân tích kỹ thuật (service analytics): chỉ báo, không phải khuyến nghị đầu tư
export const useAnOverview = () => useQuery(q("an-overview", "/analytics/overview", {}, { refetchInterval: 60_000, staleTime: 30_000 }));
export const useAnSymbol = (symbol) =>
  useQuery(q(`an-symbol-${symbol}`, `/analytics/symbol/${encodeURIComponent(symbol)}`, {}, { enabled: !!symbol, refetchInterval: 60_000, staleTime: 30_000, retry: false }));
export const useScreener = (params) => useQuery(q("an-screener", "/analytics/screener", params, { refetchInterval: 60_000, staleTime: 20_000 }));
export const useCorrelation = (tf = "D1") => useQuery(q("an-corr", "/analytics/correlation", { tf }, { refetchInterval: 300_000, staleTime: 120_000 }));
export const useSessions = () => useQuery(q("an-sessions", "/analytics/sessions", {}, { refetchInterval: 300_000, staleTime: 120_000 }));

/** Đồng hồ nhịp 1s (đếm ngược, "x giây trước"). */
export function useNow(ms = 1000) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}

export function useTheme() {
  const [theme, setTheme] = useState(document.documentElement.dataset.theme || "dark");
  // đồng bộ khi theme đổi từ nơi khác (tải prefs từ máy chủ, phím tắt, trang Danh sách theo dõi)
  useEffect(() => {
    const h = (e) => setTheme(e.detail);
    addEventListener("ts-theme", h);
    return () => removeEventListener("ts-theme", h);
  }, []);
  const set = (t) => {
    applyTheme(t);
    savePref("theme", t);
  };
  return [theme, set];
}

/** Đồng thuận theo symbol từ tín hiệu mở + vị thế net: >0 nghiêng mua. Chỉ là thống kê dữ liệu công khai. */
export function consensus(signals, positions, experts) {
  const rep = new Map((experts || []).map((e) => [e.expert_id, e.reputation?.score ?? 50]));
  const by = new Map();
  const get = (s) => {
    if (!by.has(s)) by.set(s, { symbol: s, buy: 0, sell: 0, wBuy: 0, wSell: 0, posNet: 0, posN: 0 });
    return by.get(s);
  };
  for (const s of signals || []) {
    if (s.status !== "open" || (s.side !== "buy" && s.side !== "sell")) continue;
    const r = get(s.symbol);
    const w = (rep.get(s.expert_id) ?? 50) / 100;
    if (s.side === "buy") { r.buy++; r.wBuy += w; } else { r.sell++; r.wSell += w; }
  }
  const seen = new Set();
  for (const p of positions || []) {
    const k = `${p.expert_id}|${p.source}|${p.symbol}`;
    if (seen.has(k) || p.net_volume == null) continue; // bản ghi đầu tiên = mới nhất
    seen.add(k);
    const r = get(p.symbol);
    r.posNet += Math.sign(p.net_volume);
    r.posN++;
  }
  return [...by.values()]
    .map((r) => {
      const tot = r.wBuy + r.wSell;
      return { ...r, score: tot ? (r.wBuy - r.wSell) / tot : 0, n: r.buy + r.sell + r.posN };
    })
    .sort((a, b) => b.n - a.n);
}

// Báo cáo tự động ngày/tuần (service reporter qua gateway /v1/reports): danh sách HTML/PDF, chỉ-đọc
export const useReports = () => useQuery(q("reports", "/reports", {}, { refetchInterval: 120_000, staleTime: 60_000 }));

// Rủi ro tài khoản MT/paper (service risk-monitor qua gateway /v1/risk): margin, exposure, drawdown, VaR/ES, stress. READ-ONLY
export const useRiskAccounts = () => useQuery(q("risk-accounts", "/risk/accounts", {}, { refetchInterval: 30_000, staleTime: 15_000 }));
export const useRiskAccount = (id) => useQuery(q(`risk-account-${id}`, `/risk/accounts/${encodeURIComponent(id || "")}`, {}, { enabled: !!id, refetchInterval: 30_000, staleTime: 15_000 }));

// Nhật ký giao dịch (service journal qua gateway /v1/journal): thống kê deal đã đóng, kỷ luật, MAE/MFE, review tuần. Ghi chỉ ghi chú/tag (apiWrite).
const jq = (key, acc, path, params, opts = {}) => ({
  queryKey: [`journal-${key}`, acc, params],
  queryFn: ({ signal }) => api(`/journal/${encodeURIComponent(acc || "_")}${path}`, params, signal),
  staleTime: 20_000,
  placeholderData: keepPreviousData,
  ...opts,
});
export const useJnAccounts = () =>
  useQuery({ queryKey: ["journal-accounts"], queryFn: ({ signal }) => api("/journal/accounts", {}, signal), staleTime: 30_000, refetchInterval: 60_000 });
export const useJnSummary = (acc, f) => useQuery(jq("summary", acc, "/summary", f, { enabled: !!acc, refetchInterval: 60_000 }));
export const useJnDeals = (acc, f) => useQuery(jq("deals", acc, "/deals", f, { enabled: !!acc }));
export const useJnDiscipline = (acc, f) => useQuery(jq("discipline", acc, "/discipline", f, { enabled: !!acc }));
export const useJnExcursions = (acc, f, enabled) => useQuery(jq("excursions", acc, "/excursions", f, { enabled: !!acc && !!enabled, staleTime: 60_000 }));
export const useJnReview = (acc, week) => useQuery(jq("review", acc, "/review", { week }, { enabled: !!acc && !!week }));
export const useJnNotes = (acc, kind) => useQuery(jq("notes", acc, "/notes", { kind }, { enabled: !!acc }));
