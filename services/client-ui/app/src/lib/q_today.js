// Dữ liệu cho màn "Hôm nay", banner trạng thái, yêu cầu gửi quản trị, nhắc sự kiện.
import { useEffect, useMemo, useSyncExternalStore } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiWrite } from "./api";
import { lget, lset } from "./lstore";
import { marketClosed } from "./freshness";
import { pushNotification } from "./notifstore";
import { t } from "./i18n";

// ---------- Yêu cầu gửi quản trị (tickets) ----------
export const TICKET_CATS = [
  { value: "ea_disconnected", get label() { return t("EA mất kết nối"); } },
  { value: "stale_data", get label() { return t("Dữ liệu cũ"); } },
  { value: "wrong_data", get label() { return t("Số liệu sai"); } },
  { value: "other", get label() { return t("Khác"); } },
];
export const useTickets = (enabled = true) =>
  useQuery({ queryKey: ["user-tickets"], queryFn: ({ signal }) => api("/user/tickets", {}, signal), enabled, staleTime: 15_000, refetchInterval: 60_000, retry: false });
export async function sendTicket(body) { return apiWrite("POST", "/user/tickets", body); }
export function useInvalidateTickets() { const qc = useQueryClient(); return () => qc.invalidateQueries({ queryKey: ["user-tickets"] }); }
/** Chuẩn hoá phản hồi danh sách: mảng thuần hoặc {items}. */
export const ticketItems = (d) => (Array.isArray(d) ? d : d?.items || []);

// ---------- Tiền tệ ảnh hưởng theo mã ----------
const CCY = new Set(["USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF", "CNY", "CNH", "SGD", "HKD", "SEK", "NOK", "MXN", "ZAR", "TRY", "PLN", "CZK", "HUF", "THB", "INR", "KRW", "VND"]);
const METALS = { XAU: ["XAU", "USD"], XAG: ["XAG", "USD"], XPT: ["XPT", "USD"], XPD: ["XPD", "USD"] };
const INDEX = [
  [/^(US30|DJ30|DJI|WS30|US500|SPX|SP500|NAS100|NDX|US100|USTEC|US2000)/, ["USD"]],
  [/^(GER40|GER30|DE40|DE30|DAX|EU50|STOXX|FRA40|CAC|ESP35|IT40)/, ["EUR"]],
  [/^(UK100|FTSE)/, ["GBP"]], [/^(JP225|NIKKEI|NI225|JPN225)/, ["JPY"]], [/^(AUS200|AU200)/, ["AUD"]], [/^(HK50|HSI)/, ["HKD", "CNY"]], [/^(CHINA50|CN50)/, ["CNY"]],
  [/^(USOIL|UKOIL|XTI|XBR|WTI|BRENT|OIL|NGAS|XNG)/, ["USD"]], [/^(BTC|ETH|SOL|XRP|BNB|DOGE|ADA|LTC)/, ["USD"]],
];
/** Mã -> các tiền tệ/tài sản mà tin kinh tế có thể ảnh hưởng. Chấp nhận hậu tố của broker (EURUSDm, EURUSD.pro, ...). Không đoán được -> []. */
export function symbolCurrencies(symbol) {
  const s = String(symbol || "").toUpperCase().replace(/^[A-Z]+:/, "").replace(/[^A-Z0-9]/g, "");
  if (!s) return [];
  if (METALS[s.slice(0, 3)]) return METALS[s.slice(0, 3)].concat(s.length >= 6 && CCY.has(s.slice(3, 6)) && s.slice(3, 6) !== "USD" ? [s.slice(3, 6)] : []);
  for (const [re, c] of INDEX) if (re.test(s)) return c;
  if (s.length >= 6 && CCY.has(s.slice(0, 3)) && CCY.has(s.slice(3, 6))) return [s.slice(0, 3), s.slice(3, 6)];
  return [];
}
const COUNTRY_CCY = {
  US: "USD", USA: "USD", EU: "EUR", EZ: "EUR", EMU: "EUR", DE: "EUR", FR: "EUR", IT: "EUR", ES: "EUR", NL: "EUR", UK: "GBP", GB: "GBP", JP: "JPY", AU: "AUD", NZ: "NZD",
  CA: "CAD", CH: "CHF", CN: "CNY", SG: "SGD", HK: "HKD", SE: "SEK", NO: "NOK", MX: "MXN", ZA: "ZAR", TR: "TRY", VN: "VND", IN: "INR", KR: "KRW",
};
/** Sự kiện lịch -> tiền tệ (ưu tiên trường currency của máy chủ, nếu không thì suy từ mã quốc gia). */
export const eventCurrency = (e) => {
  const c = String(e?.currency || "").toUpperCase();
  return CCY.has(c) ? c : COUNTRY_CCY[String(e?.country || "").toUpperCase()] || null;
};
/** Sự kiện trong horizon giờ ảnh hưởng tập mã đang giữ: [{event, ts, symbols[], ccy}]. */
export function eventsForPositions(events, symbols, nowMs, horizonH = 24) {
  const map = new Map(); // ccy -> symbols
  for (const s of symbols) for (const c of symbolCurrencies(s)) { if (!map.has(c)) map.set(c, []); map.get(c).push(s); }
  const out = [];
  for (const e of events || []) {
    const ts = new Date(e.ts).getTime();
    if (!Number.isFinite(ts) || ts < nowMs - 5 * 60e3 || ts > nowMs + horizonH * 3600e3) continue;
    const c = eventCurrency(e), syms = c ? map.get(c) : null;
    if (syms?.length) out.push({ event: e, ts, ccy: c, symbols: [...new Set(syms)] });
  }
  return out.sort((a, b) => a.ts - b.ts);
}

/** Tài khoản đang giữ mã nào + thị trường có đóng cửa không (để không báo lỗi giả cuối tuần). */
export const closedFor = (symbols, nowMs) => {
  const list = symbols?.length ? symbols : ["EURUSD"];
  return list.every((s) => marketClosed(s, nowMs));
};
export const currencyOf = (acc, snap) => String(snap?.currency || acc?.currency || "").toUpperCase();

// ---------- Nhắc trước sự kiện (cục bộ trên thiết bị: toast + thông báo trình duyệt nếu đã cấp quyền) ----------
const RKEY = "tc-reminders";
let reminders = lget(RKEY, []);
const subs = new Set();
const emit = () => subs.forEach((f) => f());
const save = () => { lset(RKEY, reminders); emit(); };
const sub = (f) => { subs.add(f); return () => subs.delete(f); };
export const useReminders = () => useSyncExternalStore(sub, () => reminders);
export const reminderId = (eventId, mins) => `${eventId}:${mins}`;
export function toggleReminder({ eventId, title, ts, mins }) {
  const id = reminderId(eventId, mins);
  if (reminders.some((r) => r.id === id)) reminders = reminders.filter((r) => r.id !== id);
  else reminders = [...reminders, { id, eventId, title, ts, mins, fireAt: ts - mins * 60e3 }].slice(-40);
  save();
}
/** Chạy ngầm: tới giờ thì bắn toast. Gắn một lần trong Shell. */
export function useReminderEngine() {
  const list = useReminders();
  useEffect(() => {
    if (!list.length) return undefined;
    const tick = () => {
      const now = Date.now();
      const due = reminders.filter((r) => r.fireAt <= now);
      if (!due.length) return;
      reminders = reminders.filter((r) => r.fireAt > now);
      save();
      for (const r of due) {
        if (r.ts < now - 10 * 60e3) continue; // quá muộn (mở lại app sau lâu) thì bỏ
        const title = t("Sắp có tin: {name}", { name: r.title });
        const body = r.ts > now ? t("Còn khoảng {n} phút nữa. Giá có thể biến động mạnh.", { n: Math.max(1, Math.round((r.ts - now) / 60e3)) }) : t("Sự kiện đang diễn ra. Giá có thể biến động mạnh.");
        pushNotification({ id: `rem:${r.id}`, level: "warn", kind: "reminder", title, body, toast: true });
        try { if (document.hidden && typeof Notification !== "undefined" && Notification.permission === "granted") new Notification(title, { body }); } catch { /* bỏ qua */ }
      }
    };
    tick();
    const h = setInterval(tick, 15_000);
    return () => clearInterval(h);
  }, [list.length]);
}

// ---------- Báo cáo của tôi (API theo khách hàng chưa có ở backend: 404 -> giao diện dùng dữ liệu mẫu có cờ) ----------
export const useMyReports = (accountId) =>
  useQuery({ queryKey: ["account-reports", accountId], enabled: !!accountId, queryFn: ({ signal }) => api("/account-reports", { account_id: accountId }, signal), staleTime: 60_000, retry: false });

export function useCalendarWindow(hours = 24) {
  const bucket = Math.floor(Date.now() / (5 * 60e3));
  const params = useMemo(() => {
    const from = new Date(bucket * 5 * 60e3 - 10 * 60e3), to = new Date(bucket * 5 * 60e3 + hours * 3600e3);
    return { from: from.toISOString(), to: to.toISOString(), impact: "high,med", order: "asc", limit: 300 };
  }, [bucket, hours]);
  return useQuery({ queryKey: ["calendar", params], queryFn: ({ signal }) => api("/calendar", params, signal), staleTime: 60_000, refetchInterval: 120_000, retry: false });
}
