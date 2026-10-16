// Giờ mở cửa & ngày lễ các sàn/thị trường: dữ liệu tĩnh + hàm thuần. THAM KHẢO — luôn kiểm tra lịch chính thức của sàn.
// Múi giờ/DST xử lý bằng Intl.DateTimeFormat (IANA). Không phụ thuộc thư viện ngoài.

export const MARKET_NOTE = "Giờ và ngày lễ chỉ để tham khảo (có thể thay đổi, phiên rút ngắn không được tính). Hãy kiểm tra lịch chính thức của sàn.";

const WK = [1, 2, 3, 4, 5];
const hm = (s) => { const [h, m] = s.split(":").map(Number); return h * 60 + m; };
const norm = (arr) => arr.map(([a, b]) => [hm(a), hm(b)]);

/** sessions: mảng [[mở,đóng],...] giờ địa phương áp dụng Thứ 2-6; hoặc đối tượng {dow: [[..]]} (0 = Chủ nhật). */
export const MARKETS = [
  { id: "hose", name: "Hà Nội / HOSE", short: "VN", tz: "Asia/Ho_Chi_Minh", cal: "vn", sessions: norm([["09:00", "11:30"], ["13:00", "15:00"]]), color: "var(--down)" },
  { id: "tokyo", name: "Tokyo (TSE)", short: "Tokyo", tz: "Asia/Tokyo", cal: "jp", sessions: norm([["09:00", "11:30"], ["12:30", "15:30"]]), color: "var(--info)" },
  { id: "hk", name: "Hồng Kông (HKEX)", short: "HK", tz: "Asia/Hong_Kong", cal: "hk", sessions: norm([["09:30", "12:00"], ["13:00", "16:00"]]), color: "#c58bff" },
  { id: "sydney", name: "Sydney (ASX)", short: "Sydney", tz: "Australia/Sydney", cal: "au", sessions: norm([["10:00", "16:00"]]), color: "#6fd16f" },
  { id: "frankfurt", name: "Frankfurt (Xetra)", short: "Frankfurt", tz: "Europe/Berlin", cal: "de", sessions: norm([["09:00", "17:30"]]), color: "#f0b84f" },
  { id: "london", name: "London (LSE)", short: "London", tz: "Europe/London", cal: "uk", sessions: norm([["08:00", "16:30"]]), color: "var(--accent)" },
  { id: "newyork", name: "New York (NYSE)", short: "New York", tz: "America/New_York", cal: "us", sessions: norm([["09:30", "16:00"]]), color: "var(--up)" },
  {
    id: "fx", name: "Forex (24/5)", short: "Forex", tz: "America/New_York", weekly: true, color: "#5aa9ff",
    sessions: { 0: norm([["17:00", "24:00"]]), 1: norm([["00:00", "24:00"]]), 2: norm([["00:00", "24:00"]]), 3: norm([["00:00", "24:00"]]), 4: norm([["00:00", "24:00"]]), 5: norm([["00:00", "17:00"]]) },
  },
  {
    id: "gold", name: "Vàng / CFD", short: "Vàng", tz: "America/New_York", weekly: true, color: "#ff9f5a",
    sessions: { 0: norm([["18:00", "24:00"]]), 1: norm([["00:00", "17:00"], ["18:00", "24:00"]]), 2: norm([["00:00", "17:00"], ["18:00", "24:00"]]), 3: norm([["00:00", "17:00"], ["18:00", "24:00"]]), 4: norm([["00:00", "17:00"], ["18:00", "24:00"]]), 5: norm([["00:00", "17:00"]]) },
  },
  { id: "crypto", name: "Tiền ảo (24/7)", short: "Crypto", tz: "UTC", always: true, color: "#7be0c3" },
];
export const marketById = (id) => MARKETS.find((m) => m.id === id);

// ------------------------------------------------------------------ múi giờ
const fmtCache = new Map();
function dtf(tz) {
  let f = fmtCache.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat("en-US", { timeZone: tz, hourCycle: "h23", year: "numeric", month: "numeric", day: "numeric", hour: "numeric", minute: "numeric", second: "numeric", weekday: "short" });
    fmtCache.set(tz, f);
  }
  return f;
}
const DOW = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
/** Thành phần giờ địa phương của mốc ts (ms). dow: 0 = Chủ nhật. */
export function tzParts(tz, ts) {
  const o = {};
  for (const p of dtf(tz).formatToParts(new Date(ts))) o[p.type] = p.value;
  return { y: +o.year, m: +o.month, d: +o.day, h: (+o.hour) % 24, mi: +o.minute, s: +o.second, dow: DOW[o.weekday] ?? 0 };
}
function tzOffsetMs(tz, ts) {
  const p = tzParts(tz, ts);
  return Date.UTC(p.y, p.m - 1, p.d, p.h, p.mi, p.s) - Math.floor(ts / 1000) * 1000;
}
/** Giờ địa phương (phút từ 0h) -> mốc UTC ms. minutes có thể = 1440. */
export function zonedToUtc(tz, y, m, d, minutes) {
  const guess = Date.UTC(y, m - 1, d, 0, minutes);
  const t1 = guess - tzOffsetMs(tz, guess);
  return guess - tzOffsetMs(tz, t1);
}
/** "HH:mm" giờ địa phương. */
export function localHM(tz, ts) {
  const p = tzParts(tz, ts);
  return `${String(p.h).padStart(2, "0")}:${String(p.mi).padStart(2, "0")}`;
}

// ------------------------------------------------------------------ ngày lễ
const pad = (n) => String(n).padStart(2, "0");
const key = (y, m, d) => `${y}-${pad(m)}-${pad(d)}`; // m: 1-12
const utcDow = (y, m, d) => new Date(Date.UTC(y, m - 1, d)).getUTCDay();
const addDays = (y, m, d, n) => { const t = new Date(Date.UTC(y, m - 1, d + n)); return [t.getUTCFullYear(), t.getUTCMonth() + 1, t.getUTCDate()]; };
function nthDow(y, m, dow, n) { // thứ dow thứ n của tháng
  const first = utcDow(y, m, 1);
  return 1 + ((dow - first + 7) % 7) + (n - 1) * 7;
}
function lastDow(y, m, dow) {
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return last - ((utcDow(y, m, last) - dow + 7) % 7);
}
function easter(y) { // thuật toán Gregorian ẩn danh
  const a = y % 19, b = Math.floor(y / 100), c = y % 100, d = Math.floor(b / 4), e = b % 4, f = Math.floor((b + 8) / 25), g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30, i = Math.floor(c / 4), k = c % 4, l = (32 + 2 * e + 2 * i - h - k) % 7, mm = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * mm + 114) / 31), day = ((h + l - 7 * mm + 114) % 31) + 1;
  return [y, month, day];
}
const put = (map, y, m, d, name) => { map.set(key(y, m, d), name); };
/** Quan sát: rơi T7 -> T6 trước, CN -> T2 sau (quy tắc Mỹ). */
function observedUS(y, m, d) {
  const w = utcDow(y, m, d);
  if (w === 6) return addDays(y, m, d, -1);
  if (w === 0) return addDays(y, m, d, 1);
  return [y, m, d];
}
/** CN -> T2 sau (nhiều thị trường), T7 giữ nguyên. */
function sunToMon(y, m, d) { return utcDow(y, m, d) === 0 ? addDays(y, m, d, 1) : [y, m, d]; }

function usHolidays(y) {
  const h = new Map();
  // New Year: rơi T7 thì NYSE không nghỉ bù vào T6
  if (utcDow(y, 1, 1) !== 6) { const [a, b, c] = sunToMon(y, 1, 1); put(h, a, b, c, "Tết Dương lịch"); }
  put(h, y, 1, nthDow(y, 1, 1, 3), "Martin Luther King Jr. Day");
  put(h, y, 2, nthDow(y, 2, 1, 3), "Presidents' Day");
  { const [a, b, c] = addDays(...easter(y), -2); put(h, a, b, c, "Thứ Sáu Tuần Thánh"); }
  put(h, y, 5, lastDow(y, 5, 1), "Memorial Day");
  { const [a, b, c] = observedUS(y, 6, 19); put(h, a, b, c, "Juneteenth"); }
  { const [a, b, c] = observedUS(y, 7, 4); put(h, a, b, c, "Quốc khánh Mỹ (4/7)"); }
  put(h, y, 9, nthDow(y, 9, 1, 1), "Labor Day");
  put(h, y, 11, nthDow(y, 11, 4, 4), "Thanksgiving");
  { const [a, b, c] = observedUS(y, 12, 25); put(h, a, b, c, "Giáng sinh"); }
  return h;
}
function ukHolidays(y) {
  const h = new Map();
  { const [a, b, c] = sunToMon(y, 1, 1); const w = utcDow(y, 1, 1); const t = w === 6 ? addDays(y, 1, 1, 2) : [a, b, c]; put(h, t[0], t[1], t[2], "Tết Dương lịch"); }
  const e = easter(y);
  { const [a, b, c] = addDays(...e, -2); put(h, a, b, c, "Thứ Sáu Tuần Thánh"); }
  { const [a, b, c] = addDays(...e, 1); put(h, a, b, c, "Thứ Hai Phục sinh"); }
  put(h, y, 5, nthDow(y, 5, 1, 1), "Early May bank holiday");
  put(h, y, 5, lastDow(y, 5, 1), "Spring bank holiday");
  put(h, y, 8, lastDow(y, 8, 1), "Summer bank holiday");
  const x = utcDow(y, 12, 25), b = utcDow(y, 12, 26);
  put(h, y, 12, x === 0 || x === 6 ? 27 : 25, "Giáng sinh");
  put(h, y, 12, b === 0 || b === 6 ? 28 : 26, "Boxing Day");
  return h;
}
function deHolidays(y) { // Xetra
  const h = new Map();
  put(h, y, 1, 1, "Tết Dương lịch");
  const e = easter(y);
  { const [a, b, c] = addDays(...e, -2); put(h, a, b, c, "Thứ Sáu Tuần Thánh"); }
  { const [a, b, c] = addDays(...e, 1); put(h, a, b, c, "Thứ Hai Phục sinh"); }
  put(h, y, 5, 1, "Quốc tế Lao động");
  put(h, y, 12, 24, "Đêm Giáng sinh");
  put(h, y, 12, 25, "Giáng sinh");
  put(h, y, 12, 26, "Lễ Giáng sinh thứ hai");
  put(h, y, 12, 31, "Giao thừa");
  return h;
}
function auHolidays(y) { // ASX
  const h = new Map();
  { const [a, b, c] = sunToMon(y, 1, 1); put(h, a, b, c, "Tết Dương lịch"); }
  { const w = utcDow(y, 1, 26); const t = w === 6 ? addDays(y, 1, 26, 2) : w === 0 ? addDays(y, 1, 26, 1) : [y, 1, 26]; put(h, t[0], t[1], t[2], "Australia Day"); }
  const e = easter(y);
  { const [a, b, c] = addDays(...e, -2); put(h, a, b, c, "Thứ Sáu Tuần Thánh"); }
  { const [a, b, c] = addDays(...e, 1); put(h, a, b, c, "Thứ Hai Phục sinh"); }
  { const [a, b, c] = sunToMon(y, 4, 25); put(h, a, b, c, "Anzac Day"); }
  put(h, y, 6, nthDow(y, 6, 1, 2), "Sinh nhật Nhà vua");
  const x = utcDow(y, 12, 25), b = utcDow(y, 12, 26);
  put(h, y, 12, x === 0 || x === 6 ? 27 : 25, "Giáng sinh");
  put(h, y, 12, b === 0 || b === 6 ? 28 : 26, "Boxing Day");
  return h;
}
const T = {
  jp: {
    2026: [[1, 1, "Tết Dương lịch"], [1, 2, "Nghỉ cuối năm sàn Tokyo"], [1, 3, "Nghỉ cuối năm sàn Tokyo"], [1, 12, "Ngày Thành nhân"], [2, 11, "Ngày Quốc gia thành lập"], [2, 23, "Sinh nhật Nhật hoàng"], [3, 20, "Xuân phân"], [4, 29, "Ngày Showa"], [5, 4, "Ngày Xanh"], [5, 5, "Ngày Thiếu nhi"], [5, 6, "Nghỉ bù (Hiến pháp)"], [7, 20, "Ngày Biển"], [8, 11, "Ngày Núi"], [9, 21, "Kính lão"], [9, 22, "Ngày nghỉ công dân"], [9, 23, "Thu phân"], [10, 12, "Ngày Thể thao"], [11, 3, "Ngày Văn hoá"], [11, 23, "Tạ ơn lao động"], [12, 31, "Nghỉ cuối năm sàn Tokyo"]],
    2027: [[1, 1, "Tết Dương lịch"], [1, 11, "Ngày Thành nhân"], [2, 11, "Ngày Quốc gia thành lập"], [2, 23, "Sinh nhật Nhật hoàng"], [3, 22, "Nghỉ bù (Xuân phân)"], [4, 29, "Ngày Showa"], [5, 3, "Ngày Hiến pháp"], [5, 4, "Ngày Xanh"], [5, 5, "Ngày Thiếu nhi"], [7, 19, "Ngày Biển"], [8, 11, "Ngày Núi"], [9, 20, "Kính lão"], [9, 23, "Thu phân"], [10, 11, "Ngày Thể thao"], [11, 3, "Ngày Văn hoá"], [11, 23, "Tạ ơn lao động"], [12, 31, "Nghỉ cuối năm sàn Tokyo"]],
  },
  vn: {
    2026: [[1, 1, "Tết Dương lịch"], [2, 14, "Tết Nguyên đán"], [2, 15, "Tết Nguyên đán"], [2, 16, "Tết Nguyên đán"], [2, 17, "Tết Nguyên đán"], [2, 18, "Tết Nguyên đán"], [2, 19, "Tết Nguyên đán"], [2, 20, "Tết Nguyên đán"], [2, 21, "Tết Nguyên đán"], [2, 22, "Tết Nguyên đán"], [4, 26, "Giỗ Tổ Hùng Vương"], [4, 27, "Nghỉ bù Giỗ Tổ"], [4, 30, "Giải phóng miền Nam"], [5, 1, "Quốc tế Lao động"], [9, 1, "Nghỉ Quốc khánh"], [9, 2, "Quốc khánh"]],
    2027: [[1, 1, "Tết Dương lịch"], [2, 4, "Tết Nguyên đán"], [2, 5, "Tết Nguyên đán"], [2, 6, "Tết Nguyên đán"], [2, 7, "Tết Nguyên đán"], [2, 8, "Tết Nguyên đán"], [2, 9, "Tết Nguyên đán"], [2, 10, "Tết Nguyên đán"], [4, 16, "Giỗ Tổ Hùng Vương"], [4, 30, "Giải phóng miền Nam"], [5, 3, "Nghỉ bù Quốc tế Lao động"], [9, 2, "Quốc khánh"], [9, 3, "Nghỉ Quốc khánh"]],
  },
  hk: {
    2026: [[2, 17, "Tết Âm lịch"], [2, 18, "Tết Âm lịch"], [2, 19, "Tết Âm lịch"], [4, 7, "Thanh minh (nghỉ bù)"], [5, 25, "Phật đản (nghỉ bù)"], [6, 19, "Tết Đoan ngọ"], [10, 19, "Trùng Cửu (nghỉ bù)"]],
    2027: [[2, 8, "Tết Âm lịch"], [2, 9, "Tết Âm lịch"], [4, 5, "Thanh minh"], [5, 13, "Phật đản"], [6, 9, "Tết Đoan ngọ"], [9, 16, "Sau Tết Trung thu"], [10, 8, "Trùng Cửu"]],
  },
};
function tableHolidays(cal, y) {
  const h = new Map();
  for (const [m, d, n] of T[cal]?.[y] || []) put(h, y, m, d, n);
  return h;
}
function hkHolidays(y) {
  const h = tableHolidays("hk", y);
  { const [a, b, c] = sunToMon(y, 1, 1); put(h, a, b, c, "Tết Dương lịch"); }
  const e = easter(y);
  { const [a, b, c] = addDays(...e, -2); put(h, a, b, c, "Thứ Sáu Tuần Thánh"); }
  { const [a, b, c] = addDays(...e, 1); if (!h.has(key(a, b, c))) put(h, a, b, c, "Thứ Hai Phục sinh"); }
  { const [a, b, c] = sunToMon(y, 5, 1); put(h, a, b, c, "Quốc tế Lao động"); }
  { const [a, b, c] = sunToMon(y, 7, 1); put(h, a, b, c, "Ngày thành lập HKSAR"); }
  { const [a, b, c] = sunToMon(y, 10, 1); put(h, a, b, c, "Quốc khánh Trung Quốc"); }
  { const [a, b, c] = sunToMon(y, 12, 25); put(h, a, b, c, "Giáng sinh"); }
  return h;
}
const CALS = { us: usHolidays, uk: ukHolidays, de: deHolidays, au: auHolidays, hk: hkHolidays, jp: (y) => tableHolidays("jp", y), vn: (y) => tableHolidays("vn", y) };
const holCache = new Map();
function holidaysOf(cal, y) {
  const k = `${cal}:${y}`;
  let m = holCache.get(k);
  if (!m) { m = CALS[cal] ? CALS[cal](y) : new Map(); holCache.set(k, m); }
  return m;
}
/** Tên ngày lễ của ngày địa phương (y, m 1-12, d), hoặc null. Dữ liệu cứng cho Nhật/VN/HK chỉ có 2026-2027. */
export function holidayName(market, y, m, d) {
  if (!market.cal) return null;
  return holidaysOf(market.cal, y).get(key(y, m, d)) || null;
}
/** Có dữ liệu ngày lễ cho năm này không (để cảnh báo ngoài 2026-2027 với bảng cứng). */
export const holidayYearKnown = (market, y) => !market.cal || !T[market.cal] || !!T[market.cal][y];

/** Ngày lễ sắp tới (rơi vào ngày thường): [{date:"YYYY-MM-DD", name, ts, dow}]. */
export function upcomingHolidays(market, from = new Date(), n = 5, withinDays = 400) {
  if (!market.cal) return [];
  const p = tzParts(market.tz, +from);
  const out = [];
  for (let k = 0; k <= withinDays && out.length < n; k++) {
    const [y, m, d] = addDays(p.y, p.m, p.d, k);
    const name = holidayName(market, y, m, d);
    const dow = utcDow(y, m, d);
    if (name && dow >= 1 && dow <= 5) out.push({ date: key(y, m, d), name, dow, daysAway: k, ts: zonedToUtc(market.tz, y, m, d, 0) });
  }
  return out;
}

// ------------------------------------------------------------------ trạng thái phiên
function sessionsFor(market, dow) {
  if (Array.isArray(market.sessions)) return dow >= 1 && dow <= 5 ? market.sessions : [];
  return market.sessions?.[dow] || [];
}
/** Các khoảng mở cửa (UTC ms) gộp liền kề, từ `back` ngày trước đến `fwd` ngày sau ngày địa phương của ts. */
export function openIntervals(market, ts, back = 0, fwd = 14) {
  if (market.always) return [[ts - back * 864e5, ts + fwd * 864e5]];
  const p = tzParts(market.tz, ts);
  const list = [];
  for (let k = -back; k <= fwd; k++) {
    const [y, m, d] = addDays(p.y, p.m, p.d, k);
    if (holidayName(market, y, m, d)) continue;
    for (const [a, b] of sessionsFor(market, utcDow(y, m, d))) list.push([zonedToUtc(market.tz, y, m, d, a), zonedToUtc(market.tz, y, m, d, b)]);
  }
  list.sort((x, y) => x[0] - y[0]);
  const merged = [];
  for (const iv of list) {
    const last = merged[merged.length - 1];
    if (last && iv[0] <= last[1]) last[1] = Math.max(last[1], iv[1]);
    else merged.push([iv[0], iv[1]]);
  }
  return merged;
}

/** Trạng thái tại thời điểm `date`: {open, nextChange (ms|null), reason}. reason: "phiên" | "nghỉ trưa" | "cuối tuần" | "ngày lễ: <tên>" | "ngoài giờ". */
export function statusAt(market, date = new Date()) {
  const ts = +date;
  if (market.always) return { open: true, nextChange: null, reason: "phiên" };
  const iv = openIntervals(market, ts, 0, 14);
  const cur = iv.find(([a, b]) => ts >= a && ts < b);
  if (cur) return { open: true, nextChange: cur[1], reason: "phiên" };
  const nxt = iv.find(([a]) => a > ts);
  const p = tzParts(market.tz, ts);
  const hol = holidayName(market, p.y, p.m, p.d);
  let reason;
  if (hol) reason = `ngày lễ: ${hol}`;
  else if (p.dow === 0 || p.dow === 6 || (market.weekly && p.dow === 5)) reason = "cuối tuần";
  else {
    const ss = sessionsFor(market, p.dow);
    const now = p.h * 60 + p.mi;
    reason = ss.length > 1 && now >= ss[0][1] && now < ss[ss.length - 1][0] ? "nghỉ trưa" : "ngoài giờ";
  }
  return { open: false, nextChange: nxt ? nxt[0] : null, reason };
}
