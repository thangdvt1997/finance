// Lịch kinh tế nâng cao: tuần theo giờ VN, phân nhóm chỉ số, đồng tiền theo quốc gia, cụm sự kiện (cửa sổ rủi ro), nhắc trước sự kiện, xuất CSV.
import { useEffect, useState } from "react";
import { fmtCfg } from "../ux/fmtconfig";
import { lget, lset } from "./lstore";
import { notify } from "../ux/bus";
import { effectiveTz } from "../ux/settings";
import "../intel.css";

export const DAY_MS = 86400e3;

// Ngày/tuần theo MÚI GIỜ HIỂN THỊ do người dùng chọn (Cài đặt) để cột ngày khớp với giờ in trên thẻ sự kiện.
const tzNow = () => fmtCfg.tz || "Asia/Ho_Chi_Minh";
const partsIn = (t, tz) => Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })
  .formatToParts(new Date(t)).map((x) => [x.type, x.value]));
const offsetAt = (t, tz) => { const p = partsIn(t, tz); return Date.UTC(+p.year, +p.month - 1, +p.day, p.hour === "24" ? 0 : +p.hour, +p.minute, +p.second) - Math.floor(t / 1000) * 1000; };
/** Thời điểm 00:00 của ngày (y,m,d) theo múi giờ tz (xử lý DST). d vượt giới hạn tháng được chuẩn hoá. */
export function zonedMidnight(y, m, d, tz = tzNow()) {
  const g = Date.UTC(y, m - 1, d);
  let t = g - offsetAt(g, tz);
  const o2 = offsetAt(t, tz);
  if (g - o2 !== t) t = g - o2;
  return new Date(t);
}
/** Khoá ngày YYYY-MM-DD của một thời điểm theo múi giờ hiển thị. */
export const dayKeyOf = (v, tz = tzNow()) => { const p = partsIn(+new Date(v), tz); return `${p.year}-${p.month}-${p.day}`; };
/** Thứ Hai 00:00 của tuần cách hôm nay `offset` tuần (múi giờ hiển thị). */
export function vnWeekStart(offset = 0, now = new Date(), tz = tzNow()) {
  const p = partsIn(+now, tz);
  const dow = (new Date(Date.UTC(+p.year, +p.month - 1, +p.day)).getUTCDay() + 6) % 7; // 0 = Thứ Hai
  return zonedMidnight(+p.year, +p.month, +p.day - dow + offset * 7, tz);
}
export function weekDays(start, tz = tzNow()) {
  const p = partsIn(+start, tz);
  return Array.from({ length: 7 }, (_, i) => zonedMidnight(+p.year, +p.month, +p.day + i, tz));
}
export const weekEnd = (start, tz = tzNow()) => { const p = partsIn(+start, tz); return new Date(zonedMidnight(+p.year, +p.month, +p.day + 7, tz).getTime() - 1000); };
export const dayKey = (d) => dayKeyOf(new Date(d.getTime() + 1000));

export const CCY_OF = { US: "USD", EU: "EUR", EA: "EUR", DE: "EUR", FR: "EUR", IT: "EUR", ES: "EUR", GB: "GBP", UK: "GBP", JP: "JPY", CH: "CHF", CA: "CAD", AU: "AUD", NZ: "NZD", CN: "CNY", VN: "VND" };
export const COUNTRY_NAME = { US: "Hoa Kỳ", EU: "Khu vực đồng euro", EA: "Khu vực đồng euro", DE: "Đức", FR: "Pháp", IT: "Ý", ES: "Tây Ban Nha", GB: "Anh", UK: "Anh", JP: "Nhật Bản", CH: "Thụy Sĩ", CA: "Canada", AU: "Úc", NZ: "New Zealand", CN: "Trung Quốc", VN: "Việt Nam" };

export const GROUPS = [
  { id: "cb", label: "Ngân hàng trung ương", re: /(interest rate|rate decision|rate statement|monetary policy|fomc|minutes|press conference|speaks|speech|governor|chair|ecb|boe|boj|rba|rbnz|snb|boc|fed |beige book|testifies|lãi suất)/i },
  { id: "infl", label: "Lạm phát", re: /(cpi|ppi|pce|inflation|price index|prices|deflator|lạm phát)/i },
  { id: "jobs", label: "Việc làm", re: /(employment|unemployment|payroll|nfp|jobless|claimant|wage|earnings|jolts|adp|labou?r|job )/i },
  { id: "growth", label: "Tăng trưởng & hoạt động", re: /(gdp|pmi|ism|industrial|retail sales|manufactur|services|consumer (confidence|sentiment)|durable|factory|business|ifo|zew|tankan|sentiment|confidence|output|production)/i },
  { id: "trade", label: "Thương mại", re: /(trade balance|exports|imports|current account|tariff)/i },
  { id: "housing", label: "Nhà ở", re: /(housing|building|home |construction|mortgage|house price)/i },
];
export const groupOf = (title) => GROUPS.find((g) => g.re.test(title || ""))?.id || "other";
export const GROUP_LABEL = { ...Object.fromEntries(GROUPS.map((g) => [g.id, g.label])), other: "Khác" };

const IMP_N = { high: 3, med: 2, low: 1 };
export const impN = (i) => IMP_N[i] || 1;
export const impCls = (i) => (i === "high" ? "hi" : i === "med" ? "med" : "lo");

/** Gom sự kiện theo mốc giờ (cùng phút) thành "cụm" để thấy cửa sổ rủi ro: [{ts, events, top}] tăng dần. */
export function slotsOf(events) {
  const m = new Map();
  for (const e of events) { const k = e.ts; if (!m.has(k)) m.set(k, []); m.get(k).push(e); }
  return [...m.entries()].sort((a, b) => Date.parse(a[0]) - Date.parse(b[0])).map(([ts, evs]) => ({ ts, events: evs, top: evs.reduce((t, e) => Math.max(t, impN(e.impact)), 0) }));
}

/** Cửa sổ rủi ro: các mốc có ≥1 tin tác động cao; gộp các mốc cách nhau ≤ 60 phút -> [{start, end, events}] */
export function riskWindows(events, gapMin = 60) {
  const hi = events.filter((e) => e.impact === "high").sort((a, b) => Date.parse(a.ts) - Date.parse(b.ts));
  const out = [];
  for (const e of hi) {
    const t = Date.parse(e.ts);
    const last = out[out.length - 1];
    if (last && t - last.end <= gapMin * 60e3) { last.end = t; last.events.push(e); }
    else out.push({ start: t, end: t, events: [e] });
  }
  return out;
}

export function toCsv(events) {
  const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const head = ["Thời gian (UTC)", "Quốc gia", "Tác động", "Sự kiện", "Thực tế", "Dự báo", "Kỳ trước"];
  return `﻿${[head, ...events.map((e) => [e.ts, e.country, e.impact, e.title, e.actual, e.forecast, e.previous])].map((r) => r.map(esc).join(",")).join("\r\n")}`;
}
export function download(name, text, mime = "text/csv;charset=utf-8") {
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const a = document.createElement("a");
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

// ---------------------------------------------------------------- nhắc trước sự kiện (trình duyệt đang mở)
const REM_KEY = "ts-cal-reminders";
const remSubs = new Set();
let rems = lget(REM_KEY, []).filter((r) => Date.parse(r.ts) > Date.now() - 3600e3);
const remSave = () => { lset(REM_KEY, rems); remSubs.forEach((f) => f(rems)); };
export const getReminders = () => rems;
export function addReminder(ev, leadMin) {
  rems = [...rems.filter((r) => !(r.id === ev.event_id && r.lead === leadMin)), { id: ev.event_id, ts: ev.ts, title: ev.title, country: ev.country, impact: ev.impact, lead: leadMin }].slice(-60);
  remSave();
}
export function removeReminder(id, lead) { rems = rems.filter((r) => !(r.id === id && r.lead === lead)); remSave(); }
export function useReminders() {
  const [v, setV] = useState(rems);
  useEffect(() => { remSubs.add(setV); return () => remSubs.delete(setV); }, []);
  return v;
}
// Bộ hẹn giờ nhắc chạy ở mức module (1 interval cho cả ứng dụng, tự khởi động khi module được nạp — stream.js nạp nền module này)
// nên nhắc vẫn hoạt động khi người dùng đang ở trang khác. Đến hạn -> notify() (toast/âm/chuông theo cài đặt chung).
const fired = new Set();
let ticker = null;
function tick() {
  const now = Date.now();
  for (const r of rems) {
    const t = Date.parse(r.ts);
    const due = t - r.lead * 60e3;
    const key = `${r.id}:${r.lead}`;
    if (now >= due && now < t + 5 * 60e3 && !fired.has(key)) {
      fired.add(key);
      notify({ key: `calrem:${key}`, cat: "alert", sev: r.impact === "high" ? "crit" : "warn", title: `Sắp ra tin: ${r.country || ""} ${r.title}`.trim(), body: `Còn khoảng ${Math.max(0, Math.round((t - now) / 60e3))} phút (nhắc trước ${r.lead} phút).`, href: "#/lich" });
    }
  }
  const keep = rems.filter((r) => Date.parse(r.ts) > now - 10 * 60e3);
  if (keep.length !== rems.length) { rems = keep; remSave(); }
}
export function ensureReminderTicker() {
  if (ticker || typeof window === "undefined") return;
  ticker = setInterval(tick, 10_000);
  tick();
}
/** Giữ tương thích: component có thể gọi để chắc chắn bộ hẹn giờ đã chạy. */
export function useReminderTicker() {
  useEffect(() => { ensureReminderTicker(); }, []);
}
ensureReminderTicker();

/** Nhãn múi giờ hiển thị hiện hành (theo Cài đặt) để gắn sau giờ. */
export function tzLabel() {
  try { const z = effectiveTz(); return z === "Asia/Ho_Chi_Minh" ? "giờ VN" : z; } catch { return "giờ VN"; }
}
