import { fmtCfg, dateLocale, numLocale, CUR_SYMBOLS } from "../ux/fmtconfig";
export const TZ = "Asia/Ho_Chi_Minh"; // múi giờ VN: dùng cho logic "ngày VN" (vnDayKey/vnDayStart); hiển thị theo cài đặt người dùng (ux/fmtconfig)
// Formatter dựng lười và làm mới khi người dùng đổi múi giờ/kiểu ngày trong Cài đặt.
let fc = { ver: -1 };
const F = (key, opts) => {
  if (fc.ver !== fmtCfg.ver) fc = { ver: fmtCfg.ver };
  return (fc[key] ??= new Intl.DateTimeFormat(dateLocale(), { timeZone: fmtCfg.tz, hour12: false, ...opts }));
};
const O_TIME = { hour: "2-digit", minute: "2-digit" }, O_TIMES = { hour: "2-digit", minute: "2-digit", second: "2-digit" };
const O_DATE = { day: "2-digit", month: "2-digit" }, O_DATEY = { day: "2-digit", month: "2-digit", year: "numeric" };

const d = (v) => (v instanceof Date ? v : new Date(v));
export const time = (v) => (v ? F("t", O_TIME).format(d(v)) : "—");
export const timeS = (v) => (v ? F("ts", O_TIMES).format(d(v)) : "—");
export const date = (v) => (v ? F("d", O_DATE).format(d(v)) : "—");
export const dateY = (v) => (v ? F("dy", O_DATEY).format(d(v)) : "—");
export const dow = (v) => F("w", { weekday: "short" }).format(d(v));
export const dateTime = (v) => (v ? `${F("d", O_DATE).format(d(v))} ${F("t", O_TIME).format(d(v))}` : "—");

/** Khoá ngày theo giờ VN: YYYY-MM-DD */
export function vnDayKey(v) {
  const p = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" })
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
  const u = a < 60 ? `${a} giây` : a < 3600 ? `${Math.round(a / 60)} phút` : a < 86400 ? `${Math.round(a / 3600)} giờ` : `${Math.round(a / 86400)} ngày`;
  return s >= 0 ? `${u} trước` : `sau ${u}`;
}
export function dur(sec) {
  if (sec == null) return "—";
  const a = Math.abs(sec);
  if (a < 60) return `${Math.round(a)} giây`;
  if (a < 3600) return `${Math.round(a / 60)} phút`;
  if (a < 86400) return `${(a / 3600).toFixed(1)} giờ`;
  return `${(a / 86400).toFixed(1)} ngày`;
}
export function countdown(target, now = Date.now()) {
  const s = Math.floor((d(target).getTime() - now) / 1000);
  if (s <= 0) return null;
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const p = (n) => String(n).padStart(2, "0");
  return h >= 24 ? `${Math.floor(h / 24)}n ${p(h % 24)}g` : `${p(h)}:${p(m)}:${p(sec)}`;
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
    : Number(n).toLocaleString(numLocale(), { minimumFractionDigits: decimals(symbol), maximumFractionDigits: decimals(symbol) });
export const money = (n, cur = "") => {
  if (n == null) return "—";
  const v = Number(n).toLocaleString(numLocale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const sym = fmtCfg.cur === "symbol" && CUR_SYMBOLS[String(cur).toUpperCase()];
  return sym ? `${sym}${v}` : `${v}${cur ? " " + cur : ""}`;
};
export const pct = (n, dp = 2) => (n == null || Number.isNaN(n) ? "—" : `${n > 0 ? "+" : ""}${n.toFixed(dp)}%`);
export const signCls = (n) => (n > 0 ? "up" : n < 0 ? "down" : "flat");
export const symbolLabel = (s) => (s || "").replace(/^[A-Za-z]+:/, "");
export const symbolMarket = (s) => (s?.startsWith("CRYPTO:") ? "Tiền ảo" : s?.startsWith("FRED:") ? "Vĩ mô" : s?.startsWith("VN:") ? "VN" : s?.startsWith("US:") ? "US" : s?.startsWith("XAU") ? "Kim loại" : "Forex");

export const IMPACT = { high: { label: "Cao", n: 3 }, med: { label: "Vừa", n: 2 }, low: { label: "Thấp", n: 1 } };

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
export const scrub = (s) => (typeof s === "string" ? s.replace(BANNED_RE, "nguồn dữ liệu").replace(BANNED_UP_RE, "nguồn dữ liệu") : s);
/** Làm sạch văn bản do máy chủ sinh: rút gọn số thập phân dài + bỏ tên nguồn. */
export const clean = (s) => scrub(tidyNums(s));
/** Tên chuyên gia/tổ chức: mã dạng "PREFIX:123" (định danh nội bộ theo nguồn) -> "Tổ chức 123"; còn lại bỏ tên nguồn. */
export const expertLabel = (n) => { const t = String(n ?? ""); const m = t.match(/^[A-Za-z0-9_]+:(.+)$/); return m ? (scrub(m[1]) !== m[1] ? "Nguồn tổng hợp" : `Tổ chức ${m[1]}`) : clean(t); };
/** Dữ liệu thử do QA/kiểm thử tạo (định danh bắt đầu bằng "qa-"/"qa_" hoặc mã QAUSD): không hiển thị trên giao diện vận hành. */
export const isQaId = (s) => /^qa([-_:]|usd$)/i.test(String(s || "")) || /(^|[:_-])qa[-_]/i.test(String(s || ""));
