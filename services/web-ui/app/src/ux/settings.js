// Kho tuỳ chọn giao diện (Cài đặt). Lưu localStorage ngay (không nháy khi tải lại) + đồng bộ lên máy chủ qua user_prefs.ux
// (PUT /user/prefs, debounce trong lib/prefs.js). Máy chủ chưa hỗ trợ trường `ux` hoặc offline -> vẫn chạy bằng localStorage.
import { useSyncExternalStore } from "react";
import { applyTheme, savePref, getPrefsState } from "../lib/prefs";
import { fmtCfg, setFmtConfig, validTz, browserTz, VN_TZ } from "./fmtconfig";

const KEY = "ts-ux";
export const DEFAULTS = {
  theme: "dark",          // auto | light | dark
  accent: "amber",        // amber | blue | green | violet | rose | cyan
  density: "comfortable", // comfortable | compact
  fontScale: 100,         // 90 | 100 | 110 | 125
  contrast: "normal",     // normal | high
  motion: "system",       // system | reduce | full
  tz: "vn",               // vn | auto (múi giờ trình duyệt) | tên IANA
  dateFmt: "vi",          // vi | en | iso
  numFmt: "en",           // en (1,234.56) | vi (1.234,56)
  currency: "code",       // code (USD) | symbol ($)
  updown: "vn",           // vn (xanh tăng/đỏ giảm) | asia (đỏ tăng/xanh giảm) | cb (xanh dương/cam, mù màu)
  toasts: true,
  sound: false, soundVol: 0.5,
  browserNotif: false,
  notifCats: { alert: true, news: true, expert: true, system: true },
  onboarded: 0,           // phiên bản tour đã xem
  t: 0,                   // thời điểm sửa gần nhất (ms) - để chọn bản mới khi đồng bộ
};
export const ACCENTS = {
  amber:  { label: "Vàng hổ phách", dark: "#f0b84f", light: "#8c5409" },
  blue:   { label: "Xanh dương",    dark: "#5aa9ff", light: "#1a62bd" },
  green:  { label: "Xanh lá",       dark: "#4ade80", light: "#17663d" },
  violet: { label: "Tím",           dark: "#b794f6", light: "#6b3fb8" },
  rose:   { label: "Hồng",          dark: "#ff7aa8", light: "#b4234f" },
  cyan:   { label: "Lục lam",       dark: "#3dd6e0", light: "#0b6b78" },
};
export const UPDOWN = {
  vn:   { label: "Xanh tăng · Đỏ giảm", sub: "Quy ước bảng điện Việt Nam và phương Tây" },
  asia: { label: "Đỏ tăng · Xanh giảm", sub: "Kiểu Trung Quốc, Nhật, Hàn" },
  cb:   { label: "Xanh dương tăng · Cam giảm", sub: "Thân thiện người mù màu đỏ-xanh" },
};

function readLocal() {
  try { const r = JSON.parse(localStorage.getItem(KEY) || "null"); return r && typeof r === "object" ? sanitize(r) : { ...DEFAULTS }; } catch { return { ...DEFAULTS }; }
}
function sanitize(o) {
  const s = { ...DEFAULTS, ...o, notifCats: { ...DEFAULTS.notifCats, ...(o?.notifCats || {}) } };
  if (!["auto", "light", "dark"].includes(s.theme)) s.theme = DEFAULTS.theme;
  if (!ACCENTS[s.accent]) s.accent = DEFAULTS.accent;
  if (!["comfortable", "compact"].includes(s.density)) s.density = DEFAULTS.density;
  if (![90, 100, 110, 125].includes(+s.fontScale)) s.fontScale = 100; else s.fontScale = +s.fontScale;
  if (!["normal", "high"].includes(s.contrast)) s.contrast = "normal";
  if (!["system", "reduce", "full"].includes(s.motion)) s.motion = "system";
  if (!["vn", "auto"].includes(s.tz) && !validTz(s.tz)) s.tz = "vn";
  if (!["vi", "en", "iso"].includes(s.dateFmt)) s.dateFmt = "vi";
  if (!["en", "vi"].includes(s.numFmt)) s.numFmt = "en";
  if (!["code", "symbol"].includes(s.currency)) s.currency = "code";
  if (!UPDOWN[s.updown]) s.updown = "vn";
  s.soundVol = Math.min(1, Math.max(0, Number(s.soundVol) || 0));
  s.t = Number(s.t) || 0;
  return s;
}

let S = readLocal();
const subs = new Set();
const subscribe = (f) => { subs.add(f); return () => subs.delete(f); };
export const getSettings = () => S;
export const useSettings = () => {
  const s = useSyncExternalStore(subscribe, getSettings, getSettings);
  return [s, updateSettings, resetSettings];
};
/** Số phiên bản định dạng: đổi khi múi giờ/kiểu ngày/số/tiền đổi (dùng làm `key` để dựng lại trang). */
export const useFmtVersion = () => useSyncExternalStore(subscribe, () => fmtCfg.ver, () => fmtCfg.ver);

export const effectiveTz = (s = S) => (s.tz === "vn" ? VN_TZ : s.tz === "auto" ? browserTz() : s.tz);
export const systemDark = () => { try { return matchMedia("(prefers-color-scheme: dark)").matches; } catch { return true; } };
export const effectiveTheme = (s = S) => (s.theme === "auto" ? (systemDark() ? "dark" : "light") : s.theme);

let lastThemeApplied = null;
let startedAt = 0, seenLoadEvt = false;
export function applyAll(s = S) {
  const el = document.documentElement;
  const ds = el.dataset;
  ds.accent = s.accent; ds.density = s.density; ds.fs = String(s.fontScale); ds.updown = s.updown; ds.contrast = s.contrast;
  ds.motion = s.motion;
  const eff = effectiveTheme(s);
  if (el.dataset.theme !== eff) { lastThemeApplied = eff; applyTheme(eff); }
  setFmtConfig({ tz: effectiveTz(s), date: s.dateFmt, num: s.numFmt, cur: s.currency });
}

function persist(s) {
  try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* ẩn danh/đầy bộ nhớ */ }
}
const nonDefault = (s) => JSON.stringify({ ...s, t: 0, onboarded: 0 }) !== JSON.stringify({ ...DEFAULTS, t: 0, onboarded: 0 });

export function updateSettings(patch) {
  const prevFmt = fmtCfg.ver;
  S = sanitize({ ...S, ...patch, t: Date.now() });
  persist(S);
  applyAll(S);
  pushServer();
  subs.forEach((f) => f());
  return prevFmt !== fmtCfg.ver;
}
export const resetSettings = () => updateSettings({ ...DEFAULTS, onboarded: S.onboarded });

function pushServer() {
  try {
    savePref("ux", S);
    const eff = effectiveTheme(S);
    if (getPrefsState().prefs?.theme !== eff) savePref("theme", eff); // giữ trường theme cũ khớp (bản UI cũ/ứng dụng khách đọc theme)
  } catch { /* chưa có prefs */ }
}

/** Gọi khi prefs máy chủ tải xong (App): chọn bản mới hơn giữa máy chủ và cục bộ. */
export function adoptServer(serverUx) {
  if (serverUx && typeof serverUx === "object" && Number(serverUx.t) > S.t) {
    S = sanitize(serverUx);
    persist(S);
  } else if (nonDefault(S) && S.t > Number(serverUx?.t || 0)) {
    pushServer();
  }
  applyAll(S);
  subs.forEach((f) => f());
}

let started = false;
export function startUx() {
  if (started) return;
  started = true;
  startedAt = Date.now();
  applyAll(S);
  // theme: theo hệ thống khi chọn "auto"
  try {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const h = () => { if (S.theme === "auto") applyAll(S); };
    mq.addEventListener("change", h);
  } catch { /* trình duyệt cũ */ }
  // đổi theme từ nơi khác (phím t / nút mặt trời): coi là lựa chọn tường minh; bỏ qua nhiễu do prefs máy chủ ghi đè ngay sau khi tải
  addEventListener("ts-theme", (e) => {
    const t = e.detail;
    if (t === lastThemeApplied) { lastThemeApplied = null; return; }
    // prefs máy chủ vừa tải xong gọi applyTheme(prefs.theme) đúng một lần: đó KHÔNG phải người dùng chọn tay -> giữ lựa chọn của Cài đặt (kể cả "auto")
    const ps = getPrefsState();
    if (!seenLoadEvt && ps.loaded && ps.available && ps.prefs?.theme === t) { seenLoadEvt = true; applyAll(S); return; }
    if ((t === "dark" || t === "light") && t !== S.theme) updateSettings({ theme: t });
  });
}
