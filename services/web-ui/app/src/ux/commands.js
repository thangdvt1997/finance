// Lệnh nhanh của Ctrl-K: danh sách lệnh tĩnh + trình phân tích cú pháp ý định ("cảnh báo eurusd 1.0850", "eurusd h4", "đổi giao diện tối").
// Trang khác (workspace, widget...) đăng ký thêm lệnh bằng registerCommandProvider(fn) với fn(query, ctx) -> mảng mục.
import { ACCENTS, DEFAULTS, effectiveTheme, getSettings, updateSettings } from "./settings";
import { appCmd, copyText } from "./actions";
const ex = () => import("./exporters"); // nạp lười: chỉ khi người dùng chạy lệnh xuất/in
import { toast } from "./bus";
import { toggleBookmark } from "./recent";

export const fold = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();

const providers = new Set();
/** Đăng ký nguồn lệnh/kết quả ngoài. Trả hàm huỷ đăng ký. fn(query, ctx) -> [{id, group, label, hint, icon?, kw?, run}] */
export function registerCommandProvider(fn) { providers.add(fn); return () => providers.delete(fn); }
export const runProviders = (query, ctx) => { const out = []; for (const p of providers) { try { out.push(...(p(query, ctx) || [])); } catch { /* nhà cung cấp lỗi không làm hỏng palette */ } } return out; };

/** Khớp mờ: mọi từ của truy vấn phải xuất hiện (chuỗi con) hoặc là dãy con; điểm cao = tốt hơn; -1 = không khớp. */
export function score(text, query) {
  const t = fold(text);
  let total = 0;
  for (const w of fold(query).split(/\s+/).filter(Boolean)) {
    const i = t.indexOf(w);
    if (i >= 0) { total += 100 - Math.min(i, 60) + (i === 0 || t[i - 1] === " " ? 30 : 0); continue; }
    let k = 0, gaps = 0;
    for (const ch of t) { if (ch === w[k]) k++; else if (k) gaps++; if (k === w.length) break; }
    if (k < w.length) return -1;
    total += 20 - Math.min(gaps, 18);
  }
  return total;
}

const TFS = ["M1", "M5", "M15", "H1", "H4", "D1"];
const NUM = /^[+-]?\d+(?:[.,]\d+)?$/;
const toNum = (s) => Number(String(s).replace(",", "."));

/**
 * Phân tích ý định từ câu gõ. Trả mảng mục động (đặt lên đầu kết quả).
 * symbols: [{symbol,label}] danh sách mã. Không bao giờ trả lệnh giao dịch.
 */
export function parseIntents(query, symbols) {
  const raw = query.trim();
  if (!raw) return [];
  const toks = fold(raw).split(/\s+/);
  const out = [];
  const bySym = new Map();
  for (const s of symbols || []) { bySym.set(fold(s.symbol), s.symbol); bySym.set(fold(s.label), s.symbol); }
  const symTok = toks.find((t) => bySym.has(t));
  const sym = symTok ? bySym.get(symTok) : null;
  const numTok = toks.find((t) => NUM.test(t));
  const tfTok = toks.find((t) => TFS.includes(t.toUpperCase()));
  const wantsAlert = toks.some((t) => ["alert", "canh", "bao", "baogia", "notify"].includes(t) || t.startsWith("canh"));
  const below = toks.some((t) => ["<", "duoi", "xuong", "giam", "below"].includes(t));
  if (sym && numTok && (wantsAlert || toks.length <= 3)) {
    const price = toNum(numTok);
    const op = below ? "lte" : "gte";
    out.push({ id: `i-alert-${sym}-${price}`, group: "Gợi ý", label: `Tạo cảnh báo: ${sym.replace(/^[A-Za-z]+:/, "")} ${below ? "≤" : "≥"} ${numTok}`, hint: "mở biểu mẫu", icon: "bell", kw: raw, intent: true,
      run: () => { location.hash = `#/canh-bao/new?symbol=${encodeURIComponent(sym)}&price=${encodeURIComponent(price)}&op=${op}`; } });
  }
  if (sym && tfTok) {
    const tf = tfTok.toUpperCase();
    out.push({ id: `i-chart-${sym}-${tf}`, group: "Gợi ý", label: `Mở biểu đồ ${sym.replace(/^[A-Za-z]+:/, "")} khung ${tf}`, hint: `#/thi-truong`, icon: "chart", kw: raw, intent: true,
      run: () => { location.hash = `#/thi-truong/${encodeURIComponent(sym)}?tf=${tf}`; } });
  }
  return out;
}

/** Danh sách lệnh tĩnh. ctx: {qc, routeId, route, label}. */
export function buildCommands(ctx) {
  const s = getSettings();
  const eff = effectiveTheme(s);
  const c = [];
  const add = (id, label, kw, run, hint = "", icon = "cmd") => c.push({ id: `c-${id}`, group: "Lệnh", label, hint, icon, kw: `${kw} ${label}`, run });
  add("theme-auto", "Giao diện: tự động theo thiết bị", "doi giao dien theme auto he thong", () => updateSettings({ theme: "auto" }), s.theme === "auto" ? "đang dùng" : "");
  add("theme-light", "Giao diện: sáng", "doi giao dien theme light sang", () => updateSettings({ theme: "light" }), s.theme === "light" ? "đang dùng" : "T");
  add("theme-dark", "Giao diện: tối", "doi giao dien theme dark toi", () => updateSettings({ theme: "dark" }), s.theme === "dark" ? "đang dùng" : "T");
  add("theme-toggle", eff === "dark" ? "Đổi sang giao diện sáng" : "Đổi sang giao diện tối", "toggle doi giao dien dark light", () => updateSettings({ theme: eff === "dark" ? "light" : "dark" }), "T");
  for (const [k, a] of Object.entries(ACCENTS)) add(`accent-${k}`, `Màu nhấn: ${a.label}`, `mau nhan accent ${k}`, () => updateSettings({ accent: k }), s.accent === k ? "đang dùng" : "");
  add("density-compact", "Mật độ: gọn (compact)", "mat do density compact gon", () => updateSettings({ density: "compact" }), s.density === "compact" ? "đang dùng" : "");
  add("density-comfy", "Mật độ: thoải mái", "mat do density comfortable thoai mai", () => updateSettings({ density: "comfortable" }), s.density === "comfortable" ? "đang dùng" : "");
  add("font-up", "Tăng cỡ chữ", "co chu font tang lon", () => { const a = [90, 100, 110, 125]; updateSettings({ fontScale: a[Math.min(a.indexOf(s.fontScale) + 1, 3)] }); });
  add("font-down", "Giảm cỡ chữ", "co chu font giam nho", () => { const a = [90, 100, 110, 125]; updateSettings({ fontScale: a[Math.max(a.indexOf(s.fontScale) - 1, 0)] }); });
  add("updown-vn", "Màu tăng/giảm: xanh tăng, đỏ giảm", "mau tang giam xanh do", () => updateSettings({ updown: "vn" }));
  add("updown-asia", "Màu tăng/giảm: đỏ tăng, xanh giảm (kiểu châu Á)", "mau tang giam do xanh chau a", () => updateSettings({ updown: "asia" }));
  add("updown-cb", "Màu tăng/giảm: xanh dương/cam (mù màu)", "mau tang giam mu mau colorblind", () => updateSettings({ updown: "cb" }));
  add("sound", s.sound ? "Tắt âm báo" : "Bật âm báo", "am bao sound tieng", () => { updateSettings({ sound: !s.sound }); toast({ tone: "info", title: !s.sound ? "Đã bật âm báo" : "Đã tắt âm báo", ttl: 2000 }); });
  add("motion", s.motion === "reduce" ? "Bật lại hiệu ứng chuyển động" : "Giảm chuyển động", "chuyen dong motion hieu ung", () => updateSettings({ motion: s.motion === "reduce" ? "system" : "reduce" }));
  add("reset-settings", "Đặt lại cài đặt giao diện về mặc định", "dat lai reset cai dat mac dinh", () => { if (confirm("Đặt lại mọi cài đặt giao diện về mặc định?")) updateSettings({ ...DEFAULTS, onboarded: s.onboarded }); });
  add("bell", "Mở trung tâm thông báo", "thong bao chuong notification bell", () => appCmd("bell"), "", "bell");
  add("help", "Xem bảng phím tắt", "phim tat shortcut keyboard", () => appCmd("help"), "?");
  add("rail", "Thu/mở thanh điều hướng", "thanh dieu huong rail sidebar thu gon", () => appCmd("rail"), "[");
  add("tour", "Xem lại hướng dẫn làm quen", "huong dan lam quen tour onboarding", () => appCmd("tour"));
  add("refresh", "Làm mới dữ liệu trang này", "lam moi refresh reload du lieu", () => { ctx.qc?.invalidateQueries(); toast({ tone: "info", title: "Đang làm mới dữ liệu…", ttl: 1800 }); });
  add("copy-link", "Sao chép liên kết trang hiện tại", "sao chep lien ket link share chia se", async () => { toast({ tone: (await copyText(location.href)) ? "ok" : "error", title: "Liên kết trang", body: "Đã sao chép (giữ nguyên mã/khung/bộ lọc)", ttl: 2500 }); });
  add("bookmark", "Đánh dấu / bỏ đánh dấu trang này", "danh dau bookmark yeu thich", () => { const on = toggleBookmark({ href: location.hash || "#/tong-quan", label: ctx.label || "Trang", kind: "page" }); toast({ tone: "ok", title: on ? "Đã đánh dấu trang" : "Đã bỏ đánh dấu", ttl: 2000 }); });
  add("print", "In / lưu PDF trang này", "in print pdf luu", async () => (await ex()).printPage());
  const tbl = async () => { const m = await ex(); const t = m.findTables(); if (!t.length) { toast({ tone: "warn", title: "Trang này không có bảng để xuất", ttl: 3000 }); return null; } return { m, t: t[0] }; };
  add("csv", "Xuất bảng đầu tiên của trang ra CSV", "xuat export csv bang", async () => { const r = await tbl(); if (r) r.m.downloadCSV(r.m.tableToMatrix(r.t.el), r.t.title); });
  add("xlsx", "Xuất bảng đầu tiên của trang ra Excel", "xuat export excel xlsx bang", async () => { const r = await tbl(); if (r) r.m.downloadXLSX(r.m.tableToMatrix(r.t.el), r.t.title); });
  return c;
}
