import { useEffect, useMemo, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { api } from "./api";
import { usePrefs } from "./prefs";
import { t } from "./i18n";
import { useLiveQuotes, useRealtimeLive } from "./useLiveQuote";
import { useRtAccounts } from "./rtAccounts";

/** Gộp giá đẩy (rt) lên kết quả REST /quotes/latest: giữ nguyên hình dạng hàng REST, chỉ ghi đè bid/ask/ts khi giá đẩy mới hơn. */
export function mergeLiveQuotes(rows, live, want) {
  if (!live || !live.size) return rows;
  const out = [];
  const seen = new Set();
  for (const r of Array.isArray(rows) ? rows : []) {
    const l = r && live.get(r.symbol);
    seen.add(r?.symbol);
    const rt = Date.parse(r?.ts);
    out.push(l && l.t && !(rt > l.t) ? { ...r, bid: l.bid, ask: l.ask, ts: new Date(l.t).toISOString() } : r);
  }
  for (const s of want || []) if (!seen.has(s) && live.get(s)?.t) out.push({ symbol: s, bid: live.get(s).bid, ask: live.get(s).ask, ts: new Date(live.get(s).t).toISOString() });
  return out;
}

/** Gateway trả 200 {empty:true} khi tài khoản chưa có dữ liệu EA: đổi thành lỗi status 404 để các trang giữ nguyên trạng thái rỗng sẵn có. */
const emptyAs404 = (d) => {
  if (d && d.empty === true) throw Object.assign(new Error("not found"), { status: 404 });
  return d;
};

const q = (key, path, params, opts = {}) => ({
  queryKey: [key, params],
  queryFn: ({ signal }) => api(path, params, signal).then(path.startsWith("/risk/accounts/") ? emptyAs404 : (d) => d),
  staleTime: 10_000,
  placeholderData: keepPreviousData,
  retry: (n, e) => n < 2 && !(e?.status >= 400 && e.status < 500),
  ...opts,
});

// ---- Theo tài khoản (gateway lọc theo danh tính; client chỉ hỏi account của mình) ----
/** Snapshot mọi tài khoản của phiên (kèm vị thế). */
export const useAccountSnaps = () => {
  const live = useRealtimeLive(); // rt đẩy a:<id> / e:<id> của CHÍNH các tài khoản trong phiên -> REST chỉ là seed/dự phòng
  const r = useQuery(q("accounts", "/accounts", {}, { refetchInterval: live ? 120_000 : 15_000 }));
  const ids = useMemo(() => (Array.isArray(r.data) ? r.data.map((a) => a?.account_id).filter(Boolean).sort().join(",") : ""), [r.data]);
  useRtAccounts(live ? ids : "", true);
  return r;
};
export const useEquity = (account_id, from) =>
  useQuery(q("equity", "/equity-history", { account_id, from, limit: 5000 }, { enabled: !!account_id, refetchInterval: 60_000 }));
export const useRiskAccount = (id) =>
  useQuery(q(`risk-account-${id}`, `/risk/accounts/${encodeURIComponent(id || "")}`, {}, { enabled: !!id, refetchInterval: 30_000, staleTime: 15_000, retry: false }));

const jq = (key, acc, path, params, opts = {}) => ({
  queryKey: [`journal-${key}`, acc, params],
  queryFn: ({ signal }) => api(`/journal/${encodeURIComponent(acc || "_")}${path}`, params, signal).then(path === "/summary" ? emptyAs404 : (d) => d),
  staleTime: 20_000, placeholderData: keepPreviousData, retry: false, ...opts,
});
export const useJnSummary = (acc, f) => useQuery(jq("summary", acc, "/summary", f, { enabled: !!acc, refetchInterval: 60_000 }));
export const useJnDeals = (acc, f) => useQuery(jq("deals", acc, "/deals", f, { enabled: !!acc }));
export const useJnDiscipline = (acc, f) => useQuery(jq("discipline", acc, "/discipline", f, { enabled: !!acc }));
export const useJnNotes = (acc, kind) => useQuery(jq("notes", acc, "/notes", { kind }, { enabled: !!acc }));

export const useRules = () => useQuery({ queryKey: ["user-rules"], queryFn: ({ signal }) => api("/user/rules", {}, signal), staleTime: 10_000, refetchInterval: 30_000, retry: false });
export const useRuleEvents = (rule_id, limit = 50) =>
  useQuery({ queryKey: ["user-rule-events", rule_id || "", limit], queryFn: ({ signal }) => api("/user/rule-events", { rule_id, limit }, signal), staleTime: 10_000, refetchInterval: 30_000, retry: false });

// ---- Dùng chung (thị trường, tin, lịch) ----
export const useSymbols = () => useQuery(q("symbols", "/symbols", {}, { staleTime: 60_000, refetchInterval: 120_000 }));
export const useQuotes = (symbols) => {
  const live = useRealtimeLive();
  const r = useQuery(q("quotes", "/quotes/latest", { symbols: symbols?.join(",") }, { refetchInterval: live ? 120_000 : 30_000, enabled: !!symbols?.length }));
  const lq = useLiveQuotes(symbols ? symbols.slice(0, 100) : undefined);
  const data = useMemo(() => mergeLiveQuotes(r.data, lq, symbols), [r.data, lq, symbols?.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps
  return data === r.data ? r : { ...r, data };
};
export const useBars = (symbol, tf, limit = 300) => {
  const live = useRealtimeLive();
  return useQuery(q("bars", "/bars", { symbol, tf, limit, order: "desc" }, { enabled: !!symbol && !!tf, refetchInterval: live ? 180_000 : 60_000 }));
};
export const useNews = (params) => useQuery(q("news", "/news", params, { refetchInterval: 60_000 }));
export const useCalendar = (params) => useQuery(q("calendar", "/calendar", params, { refetchInterval: 120_000 }));
export const useRiskAll = () => useQuery(q("risk-all", "/risk-windows", {}, { refetchInterval: 30_000, staleTime: 15_000 }));
export const useRiskSymbol = (symbol) => useQuery(q(`risk-${symbol}`, "/risk-windows", { symbol }, { enabled: !!symbol, refetchInterval: 30_000, staleTime: 15_000 }));
export const useAnSymbol = (symbol) =>
  useQuery(q(`an-symbol-${symbol}`, `/analytics/symbol/${encodeURIComponent(symbol)}`, {}, { enabled: !!symbol, refetchInterval: 60_000, staleTime: 30_000, retry: false }));
export const useAnOverview = () => useQuery(q("an-overview", "/analytics/overview", {}, { refetchInterval: 60_000, staleTime: 30_000, retry: false }));
export const useScreener = (params) => useQuery(q("an-screener", "/analytics/screener", params, { refetchInterval: 60_000, staleTime: 20_000, retry: false }));

/** Đồng hồ nhịp (đếm ngược). */
export function useNow(ms = 1000) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), ms); return () => clearInterval(t); }, [ms]);
  return now;
}

export function useTheme() {
  const { prefs, set } = usePrefs();
  const eff = document.documentElement.dataset.theme || "dark";
  return [prefs.theme === "auto" ? eff : prefs.theme, (t) => set({ theme: t })];
}

/** Trạng thái kết nối EA suy ra từ tuổi snapshot: live <= 90s, slow <= 10 phút, off > 10 phút / chưa có. */
export function eaState(ts, nowMs = Date.now()) {
  const tm = ts ? new Date(ts).getTime() : NaN;
  if (!Number.isFinite(tm)) return { level: "none", label: t("Chưa nhận dữ liệu từ EA"), ageS: null };
  const ageS = Math.max(0, (nowMs - tm) / 1000);
  if (ageS <= 90) return { level: "on", label: t("EA đang kết nối"), ageS };
  if (ageS <= 600) return { level: "warn", label: t("EA phản hồi chậm"), ageS };
  return { level: "off", label: t("EA mất kết nối"), ageS };
}
