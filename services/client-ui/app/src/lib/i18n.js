// i18n gọn (không phụ thuộc thư viện): KHOÁ = câu tiếng Việt gốc, từ điển en ở src/i18n/en/*.js (mỗi tệp: export default { "câu vi": "English" }).
// Dùng:  import { t, useT } from "../lib/i18n";   t("Tổng quan")   t("Còn {n} lệnh", { n: 3 })   (biến {name}; thiếu bản dịch -> trả câu vi).
// Số nhiều tiếng Anh: dùng 2 khoá, hoặc t("{n} lệnh", {n}) -> en "{n} order(s)". Ngôn ngữ nằm trong prefs.lang ("vi" mặc định | "en"); đổi ngôn ngữ = dựng lại cây giao diện (prefs.jsx key theo lang).
// Kiểm tra thiếu bản dịch: node scripts/i18n-check.cjs
import { Fragment, cloneElement, createElement, isValidElement } from "react";
const mods = import.meta.glob("../i18n/en/*.js", { eager: true });
const EN = {};
for (const m of Object.values(mods)) Object.assign(EN, m.default || {});

export const LANGS = [{ value: "vi", label: "Tiếng Việt" }, { value: "en", label: "English" }];
let LANG = "vi";
export const getLang = () => LANG;
export const setLang = (l) => {
  LANG = l === "en" ? "en" : "vi";
  try { document.documentElement.lang = LANG; document.title = t("Tài khoản của tôi"); } catch { /* bỏ qua */ }
};
/** Locale cho Intl theo ngôn ngữ giao diện (ngày/giờ). Số lấy theo prefs.num. */
export const dateLocale = () => (LANG === "en" ? "en-GB" : "vi-VN");

export function t(key, vars) {
  let s = LANG === "en" ? EN[key] ?? key : key;
  if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined && vars[k] !== null ? String(vars[k]) : m));
  return s;
}
/** Hook: trả về t; component tự dựng lại khi đổi ngôn ngữ nhờ key theo lang ở PrefsProvider. */
export const useT = () => t;
export const hasEn = (key) => Object.prototype.hasOwnProperty.call(EN, key);

/** Số nhiều: tn("{n} lệnh", n) — vi giữ nguyên; en lấy "một|nhiều" từ từ điển, vd "{n} order|{n} orders" (không có dấu | thì dùng nguyên chuỗi). */
export function tn(key, n, vars) {
  let s = key;
  if (LANG === "en") {
    const v = EN[key];
    if (v !== undefined) { const p = v.split("|"); s = p.length > 1 ? (Number(n) === 1 ? p[0] : p[1]) : v; }
  }
  return s.replace(/\{(\w+)\}/g, (m, k) => (k === "n" ? String(n) : vars && vars[k] != null ? String(vars[k]) : m));
}

/** Như t() nhưng biến có thể là phần tử React (nhúng <b>, <a>... vào giữa câu): tr("Bật {opt} rồi lưu", { opt: <b>WebRequest</b> }) -> Fragment. */
export function tr(key, vars) {
  const s = LANG === "en" ? EN[key] ?? key : key;
  return createElement(Fragment, null, ...s.split(/(\{\w+\})/g).map((p, i) => {
    const m = /^\{(\w+)\}$/.exec(p);
    const v = m && vars ? vars[m[1]] : undefined;
    if (v === undefined || v === null) return createElement(Fragment, { key: i }, p);
    return isValidElement(v) ? cloneElement(v, { key: i }) : createElement(Fragment, { key: i }, String(v));
  }));
}

/** Tên do máy chủ sinh có tiền tố tiếng Việt cố định ("Vị thế đầu cơ — XAU", "Báo kinh tế #3"...) -> dịch phần tiền tố khi ở en. */
export const trData = (s) => (LANG === "en" ? String(s ?? "").replace(/^(Vị thế đầu cơ|Báo kinh tế|Luồng tin)/, (m) => EN[m] ?? m) : s);
const NAME_WORDS = ["Đô la Mỹ", "Bảng Anh", "Yên Nhật", "Franc Thụy Sĩ", "Đô la Úc", "Đô la New Zealand", "Đô la Canada", "Vàng", "Bạc", "Dầu thô"];
/** Tên công cụ do máy chủ sinh (vd "Euro / Đô la Mỹ") -> dịch các từ tên tiền/kim loại khi ở en. */
export const trName = (s) => (LANG === "en" && s ? NAME_WORDS.reduce((a, w) => (EN[w] ? a.split(w).join(EN[w]) : a), String(s)) : s);
