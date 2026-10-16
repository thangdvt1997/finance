import { t, dateLocale } from "./i18n";
// Múi giờ + định dạng số theo cài đặt người dùng (lib/prefs.js gọi setFormatPrefs rồi tải lại cây giao diện).
export const VN_TZ = "Asia/Ho_Chi_Minh";
export let TZ = VN_TZ;
let NUM = "en-US";
const mk = (opts) => () => new Intl.DateTimeFormat(dateLocale(), { timeZone: TZ, hour12: false, ...opts });
let fTime, fTimeS, fDate, fDateY, fDow;
const build = () => {
  fTime = mk({ hour: "2-digit", minute: "2-digit" })(); fTimeS = mk({ hour: "2-digit", minute: "2-digit", second: "2-digit" })();
  fDate = mk({ day: "2-digit", month: "2-digit" })(); fDateY = mk({ day: "2-digit", month: "2-digit", year: "numeric" })(); fDow = mk({ weekday: "short" })();
};
export function setFormatPrefs({ tz, num } = {}) {
  NUM = num === "vi" ? "vi-VN" : "en-US";
  TZ = !tz || tz === "vn" ? VN_TZ : tz === "local" ? (Intl.DateTimeFormat().resolvedOptions().timeZone || VN_TZ) : tz;
  NUM = num === "vi" ? "vi-VN" : "en-US";
  build();
}
build();
export const numLocale = () => NUM;
const nf = (v, o) => Number(v).toLocaleString(NUM, o);

const d = (v) => (v instanceof Date ? v : new Date(v));
export const time = (v) => (v ? fTime.format(d(v)) : "—");
export const timeS = (v) => (v ? fTimeS.format(d(v)) : "—");
export const date = (v) => (v ? fDate.format(d(v)) : "—");
export const dateY = (v) => (v ? fDateY.format(d(v)) : "—");
export const dow = (v) => fDow.format(d(v));
export const dateTime = (v) => (v ? `${fDate.format(d(v))} ${fTime.format(d(v))}` : "—");

/** Khoá ngày theo giờ VN: YYYY-MM-DD */
export function vnDayKey(v) {
  const p = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", { timeZone: VN_TZ, year: "numeric", month: "2-digit", day: "2-digit" })
      .formatToParts(d(v))
      .map((x) => [x.type, x.value]),
  );
  return `${p.year}-${p.month}-${p.day}`;
}
/** Mốc 00:00 giờ VN (UTC+7, không có DST) của ngày cách hôm nay `offset` ngày. */
export function vnDayStart(offset = 0, now = new Date()) {
  const [y, m, dd] = vnDayKey(now).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, dd + offset, -7, 0, 0));
}

export function rel(v, now = Date.now()) {
  if (!v) return "—";
  const s = Math.round((now - d(v).getTime()) / 1000);
  const a = Math.abs(s);
  const u = a < 60 ? t("{n} giây", { n: a }) : a < 3600 ? t("{n} phút", { n: Math.round(a / 60) }) : a < 86400 ? t("{n} giờ", { n: Math.round(a / 3600) }) : t("{n} ngày", { n: Math.round(a / 86400) });
  return s >= 0 ? t("{u} trước", { u }) : t("sau {u}", { u });
}
export function dur(sec) {
  if (sec == null) return "—";
  const a = Math.abs(sec);
  if (a < 60) return t("{n} giây", { n: Math.round(a) });
  if (a < 3600) return t("{n} phút", { n: Math.round(a / 60) });
  if (a < 86400) return t("{n} giờ", { n: (a / 3600).toFixed(1) });
  return t("{n} ngày", { n: (a / 86400).toFixed(1) });
}
export function countdown(target, now = Date.now()) {
  const s = Math.floor((d(target).getTime() - now) / 1000);
  if (s <= 0) return null;
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const p = (n) => String(n).padStart(2, "0");
  return h >= 24 ? t("{d}n {h}g", { d: Math.floor(h / 24), h: p(h % 24) }) :`${p(h)}:${p(m)}:${p(sec)}`;
}

export function decimals(symbol) {
  if (!symbol) return 2;
  if (symbol.startsWith("VN:")) return 0;
  if (symbol.startsWith("US:")) return 2;
  if (symbol.includes("JPY")) return 3;
  if (symbol.startsWith("XAU") || symbol.startsWith("XAG")) return 2;
  if (/^(BTC|ETH)/.test(symbol)) return 1;
  return 5;
}
export const price = (symbol, n) =>
  n == null || Number.isNaN(n)
    ? "—"
    : nf(n, { minimumFractionDigits: decimals(symbol), maximumFractionDigits: decimals(symbol) });
export const money = (n, cur = "") =>
  n == null ? "—" : `${nf(n, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}${cur ? " " + cur : ""}`;
export const pct = (n, dp = 2) => (n == null || Number.isNaN(n) ? "—" : `${n > 0 ? "+" : ""}${n.toFixed(dp)}%`);
export const signCls = (n) => (n > 0 ? "up" : n < 0 ? "down" : "flat");
export const symbolLabel = (s) => (s || "").replace(/^[A-Za-z]+:/, "");
export const symbolMarket = (s) => (s?.startsWith("CRYPTO:") ? t("Tiền ảo") : s?.startsWith("FRED:") ? t("Vĩ mô") : s?.startsWith("VN:") ? t("VN") : s?.startsWith("US:") ? t("US") : s?.startsWith("XAU") ? t("Kim loại") : t("Forex"));

// nhãn dịch theo ngôn ngữ hiện tại (getter: đọc mỗi lần dùng nên đổi ngôn ngữ có hiệu lực ngay)
export const IMPACT = {
  high: { get label() { return t("Cao"); }, n: 3 },
  med: { get label() { return t("Vừa"); }, n: 2 },
  low: { get label() { return t("Thấp"); }, n: 1 },
};

/** Rút gọn số thập phân dài trong văn bản do máy chủ sinh (vd 13.439209756097561 -> 13.44) để hiển thị gọn. */
export const tidyNums = (s) => (typeof s === "string" ? s.replace(/(\d+)\.(\d{5,})/g, (m) => String(Number(Number(m).toFixed(2)))) : s);

/** Danh sách tên nguồn dữ liệu KHÔNG được hiển thị trên giao diện (kiểm tra bằng scripts/lint-sources.cjs). Giữ chữ thường. */
export const BANNED_SOURCES = ["dukascopy", "frankfurter", "yahoo", "vnstock", "vndirect", "finfo", "okx", "kucoin", "binance", "bybit", "coinbase", "kraken", "ccxt", "alpaca", "tiingo", "oanda", "truefx",
  "gdelt", "reuters", "cafef", "vnexpress", "myfxbook", "actionforex", "fair economy", "faireconomy", "forexfactory", "investinglive", "oilprice", "mql5", "kbs", "statistics canada", "eurostat", "stooq", "twelvedata", "polygon", "finnhub", "alphavantage"];
const BANNED_UP = ["BLS", "CFTC", "SEC", "ECB", "FRED", "ONS", "ABS", "FMP", "COT"]; // viết hoa, khớp nguyên từ
const NB = "(?<![\\p{L}\\p{N}])", NA = "(?![\\p{L}\\p{N}])";
const BANNED_RE = new RegExp(NB + "(" + BANNED_SOURCES.map((x) => x.replace(/ /g, "\\s+")).join("|") + ")" + NA, "giu");
const BANNED_UP_RE = new RegExp(NB + "(" + BANNED_UP.join("|") + ")" + NA, "gu");
/** Loại tên nguồn dữ liệu khỏi chuỗi hiển thị (thay bằng "nguồn dữ liệu"). */
export const scrub = (s) => (typeof s === "string" ? s.replace(BANNED_RE, t("nguồn dữ liệu")).replace(BANNED_UP_RE, t("nguồn dữ liệu")) : s);
/** Làm sạch văn bản do máy chủ sinh: rút gọn số thập phân dài + bỏ tên nguồn. */
export const clean = (s) => scrub(tidyNums(s));
/** Tên chuyên gia/tổ chức: mã dạng "PREFIX:123" (định danh nội bộ theo nguồn) -> "Tổ chức 123"; còn lại bỏ tên nguồn. */
export const expertLabel = (n) => { const s = String(n ?? ""); const m = s.match(/^[A-Za-z0-9_]+:(.+)$/); return m ? (scrub(m[1]) !== m[1] ? t("Nguồn tổng hợp") : t("Tổ chức {id}", { id: m[1] })) : clean(s); };

// ---- Bổ sung cho client-ui ----
export const smoney = (n) => (n == null || Number.isNaN(n) ? "—" : `${n > 0 ? "+" : ""}${money(n)}`);
export const f0 = (n) => (n == null || Number.isNaN(n) ? "—" : nf(n, { maximumFractionDigits: 0 }));
export const f1 = (n, dp = 1) => (n == null || Number.isNaN(n) ? "—" : nf(n, { minimumFractionDigits: dp, maximumFractionDigits: dp }));
