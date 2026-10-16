// Cài đặt giao diện của người dùng (lưu trong trình duyệt này, KHÔNG chứa dữ liệu tài khoản).
// theme: auto|light|dark · density: comfortable|compact · tz: vn|local|IANA · num: en (1,234.56) | vi (1.234,56)
import { Fragment, createContext, createElement, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { lget, lset } from "./lstore";
import { setFormatPrefs } from "./format";
import { setLang, t } from "./i18n";

export const DEFAULTS = { lang: "vi", theme: "auto", density: "comfortable", tz: "vn", num: "en", sound: false, onboarded: false, toasts: true };
const KEY = "tc-prefs";

export const TZ_OPTIONS = [
  { value: "vn", get label() { return t("Giờ Việt Nam (UTC+7)"); } }, { value: "local", get label() { return t("Giờ của thiết bị"); } },
  { value: "Asia/Singapore", label: "Singapore" }, { value: "Asia/Tokyo", label: "Tokyo" }, { value: "Europe/London", label: "London" },
  { value: "America/New_York", label: "New York" }, { value: "UTC", label: "UTC" },
];

export const loadPrefs = () => ({ ...DEFAULTS, ...(lget(KEY, {}) || {}) });

/** Áp dụng lên <html>: theme + mật độ + định dạng số/giờ. Gọi sớm (main.jsx) và mỗi lần đổi. */
export function applyPrefs(p) {
  const root = document.documentElement;
  let t = p.theme;
  if (t !== "light" && t !== "dark") t = matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  root.dataset.theme = t;
  root.dataset.density = p.density === "compact" ? "compact" : "comfortable";
  try { localStorage.setItem("tc-theme", p.theme === "auto" ? "auto" : t); } catch { /* bỏ qua */ }
  setLang(p.lang);
  setFormatPrefs({ tz: p.tz, num: p.num });
}

const Ctx = createContext(null);
export const usePrefs = () => useContext(Ctx);

export function PrefsProvider({ children }) {
  const [prefs, setPrefs] = useState(() => { const p = loadPrefs(); applyPrefs(p); return p; });
  const [ver, setVer] = useState(0);
  const [epoch, setEpoch] = useState(0); // đồng bộ từ thiết bị khác đổi danh sách theo dõi -> dựng lại cây một lần
  const set = useCallback((patch) => {
    setPrefs((cur) => {
      const n = { ...cur, ...patch };
      lset(KEY, n); applyPrefs(n);
      return n;
    });
    setVer((v) => v + 1); // buộc vẽ lại toàn bộ để áp múi giờ/định dạng số
  }, []);
  /** Áp dụng cài đặt kéo từ máy chủ (lib/prefsync.jsx): khoá giao diện qua set(); watchlist ghi vào kho cục bộ rồi dựng lại cây. */
  const applyRemote = useCallback((patch) => {
    const { watchlist, ...rest } = patch || {};
    if (Object.keys(rest).length) set(rest);
    if (watchlist) { lset("tc-wl2", watchlist); setEpoch((e) => e + 1); }
  }, [set]);
  useEffect(() => { // chế độ "tự động" theo hệ điều hành
    const mq = matchMedia("(prefers-color-scheme: light)");
    const h = () => setPrefs((cur) => { if (cur.theme === "auto") applyPrefs(cur); return cur; });
    mq.addEventListener?.("change", h);
    return () => mq.removeEventListener?.("change", h);
  }, []);
  const value = useMemo(() => ({ prefs, set, ver, applyRemote }), [prefs, set, ver, applyRemote]);
  // key theo ngôn ngữ: đổi vi/en dựng lại toàn bộ cây để mọi t() chạy lại
  return createElement(Ctx.Provider, { value }, createElement(Fragment, { key: `${prefs.lang}:${epoch}` }, children));
}
