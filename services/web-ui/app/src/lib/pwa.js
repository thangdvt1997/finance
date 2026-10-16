// PWA: đăng ký service worker (chỉ production + ngữ cảnh an toàn HTTPS/localhost), nút cài đặt, thông báo bản mới.
import { useSyncExternalStore } from "react";

const st = { canInstall: false, installed: false, updateReady: false };
let snapshot = { ...st };
const subs = new Set();
let deferred = null, waiting = null, reloading = false;
const emit = () => {
  snapshot = { ...st };
  subs.forEach((f) => f());
};

const standalone = () => window.matchMedia?.("(display-mode: standalone)").matches || navigator.standalone === true;

export function initPwa() {
  if (typeof window === "undefined") return;
  st.installed = standalone();
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferred = e;
    st.canInstall = !standalone();
    emit();
  });
  window.addEventListener("appinstalled", () => {
    deferred = null;
    st.canInstall = false;
    st.installed = true;
    emit();
  });
  // Ngữ cảnh không an toàn (http://IP) hoặc dev: bỏ qua êm, không lỗi.
  if (!import.meta.env.PROD || !window.isSecureContext || !("serviceWorker" in navigator)) return;
  const watch = (reg) => {
    const mark = (w) => {
      if (w && navigator.serviceWorker.controller) {
        waiting = w;
        st.updateReady = true;
        emit();
      }
    };
    mark(reg.waiting);
    reg.addEventListener("updatefound", () => {
      const w = reg.installing;
      w?.addEventListener("statechange", () => w.state === "installed" && mark(w));
    });
    setInterval(() => reg.update().catch(() => {}), 60 * 60 * 1000);
  };
  const go = () => navigator.serviceWorker.register("/sw.js", { scope: "/" }).then(watch).catch(() => {});
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (reloading || !waiting) return; // chỉ tải lại khi chính người dùng bấm "Tải lại"
    reloading = true;
    location.reload();
  });
  if (document.readyState === "complete") go();
  else window.addEventListener("load", go, { once: true });
}

export async function promptInstall() {
  if (!deferred) return;
  const p = deferred;
  deferred = null;
  st.canInstall = false;
  emit();
  try {
    await p.prompt();
    await p.userChoice;
  } catch {
    /* người dùng đóng hộp thoại */
  }
}
export const applyUpdate = () => waiting?.postMessage({ type: "SKIP_WAITING" });

const subscribe = (f) => {
  subs.add(f);
  return () => subs.delete(f);
};
export const usePwa = () => useSyncExternalStore(subscribe, () => snapshot);
