// Dữ liệu nền cho biểu đồ: chuyển nến API -> nến làm việc, gộp phân trang lịch sử, mã -> tiền tệ/quốc gia liên quan (lọc sự kiện lịch).
export const TF_SEC = { M1: 60, M5: 300, M15: 900, M30: 1800, H1: 3600, H4: 14400, D1: 86400, W1: 604800, MN: 2592000, MN1: 2592000 };
export const KNOWN_TFS = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN", "MN1"];
export const tfSecOf = (tf) => TF_SEC[tf] || (Number(String(tf).slice(1)) || 1) * ({ M: 60, H: 3600, D: 86400, W: 604800 }[String(tf)[0]] || 60);
export const MAX_BARS_TOTAL = 20000;

/** API (mới -> cũ) -> nến cũ -> mới, loại trùng/không tăng. */
export const toBars = (items) => {
  const out = [];
  let prev = -1;
  for (let i = items.length - 1; i >= 0; i--) {
    const b = items[i], t = Math.floor(Date.parse(b.ts_open) / 1000);
    if (!Number.isFinite(t) || t <= prev) continue;
    prev = t;
    out.push({ t, o: b.o, h: b.h, l: b.l, c: b.c, v: b.v || 0, src: b.source, ts: b.ts_open });
  }
  return out;
};

/** Gộp nến cũ (older) + nến mới nhất (latest); trùng thời gian lấy bản của latest. Cả hai đã tăng dần. */
export function mergeBars(older, latest) {
  if (!older.length) return latest;
  if (!latest.length) return older;
  const cut = latest[0].t;
  let i = older.length;
  while (i > 0 && older[i - 1].t >= cut) i--;
  return i === older.length ? [...older, ...latest] : [...older.slice(0, i), ...latest];
}

const CCY_COUNTRY = {
  USD: ["US", "USA", "UNITED STATES"], EUR: ["EU", "EZ", "EUR", "EUROZONE", "EURO", "DE", "FR", "IT", "ES"], GBP: ["GB", "UK", "UNITED KINGDOM"], JPY: ["JP", "JPN", "JAPAN"],
  AUD: ["AU", "AUS", "AUSTRALIA"], NZD: ["NZ", "NZL", "NEW ZEALAND"], CAD: ["CA", "CAN", "CANADA"], CHF: ["CH", "CHE", "SWITZERLAND"], CNY: ["CN", "CHN", "CHINA"], VND: ["VN", "VNM", "VIETNAM"],
};
/** Các tiền tệ trong mã: EURUSD -> [EUR, USD]; XAUUSD -> [USD]; VN:FPT -> [VND]; US:AAPL -> [USD]. */
export function symbolCurrencies(symbol) {
  const s = String(symbol || "").toUpperCase();
  if (s.startsWith("VN:")) return ["VND"];
  if (s.startsWith("US:")) return ["USD"];
  const m = /^([A-Z]{3})([A-Z]{3})/.exec(s);
  const out = [];
  if (m) for (const c of [m[1], m[2]]) if (CCY_COUNTRY[c]) out.push(c);
  if (/^(XAU|XAG|WTI|BRENT|USOIL|UKOIL|BTC|ETH)/.test(s) && !out.includes("USD")) out.push("USD");
  return out;
}
/** Sự kiện lịch có liên quan tới mã? (true nếu không xác định được tiền tệ) */
export function eventRelevant(symbol, country) {
  const ccys = symbolCurrencies(symbol);
  if (!ccys.length) return true;
  const c = String(country || "").toUpperCase().trim();
  if (!c) return true;
  return ccys.some((k) => CCY_COUNTRY[k].includes(c) || c === k || c.includes(CCY_COUNTRY[k][2] || "~~"));
}
