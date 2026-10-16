// Cấu hình định dạng dùng chung (múi giờ, kiểu ngày, kiểu số, ký hiệu tiền). Không phụ thuộc module nào để lib/format.js nhập được.
// settings.js ghi vào đây; format.js đọc mỗi lần định dạng (formatter được làm mới khi `ver` đổi).
export const VN_TZ = "Asia/Ho_Chi_Minh";
export const fmtCfg = { tz: VN_TZ, date: "vi", num: "en", cur: "code", ver: 0 };

export const DATE_LOCALES = { vi: "vi-VN", en: "en-GB", iso: "sv-SE" };
export const NUM_LOCALES = { en: "en-US", vi: "vi-VN" };
export const CUR_SYMBOLS = { USD: "$", EUR: "€", GBP: "£", JPY: "¥", VND: "₫", AUD: "A$", CAD: "C$", CHF: "CHF", CNY: "¥" };

export const dateLocale = () => DATE_LOCALES[fmtCfg.date] || "vi-VN";
export const numLocale = () => NUM_LOCALES[fmtCfg.num] || "en-US";

export function setFmtConfig(patch) {
  let changed = false;
  for (const [k, v] of Object.entries(patch)) if (v != null && fmtCfg[k] !== v) { fmtCfg[k] = v; changed = true; }
  if (changed) fmtCfg.ver++;
  return changed;
}

/** Múi giờ hợp lệ? (Intl ném RangeError nếu sai) */
export function validTz(tz) {
  try { new Intl.DateTimeFormat("en", { timeZone: tz }); return true; } catch { return false; }
}
export const browserTz = () => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || VN_TZ; } catch { return VN_TZ; } };

/** Nhãn offset "UTC+7" của múi giờ tại thời điểm `at`. */
export function tzOffsetLabel(tz = fmtCfg.tz, at = new Date()) {
  try {
    const p = new Intl.DateTimeFormat("en-US", { timeZone: tz, timeZoneName: "shortOffset" }).formatToParts(at).find((x) => x.type === "timeZoneName")?.value || "";
    return p.replace("GMT", "UTC") || "UTC";
  } catch { return "UTC"; }
}
export const isVnTz = () => fmtCfg.tz === VN_TZ;
