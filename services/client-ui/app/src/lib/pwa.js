// Đăng ký service worker (phạm vi /c/). SW chỉ cache tệp tĩnh; KHÔNG bao giờ cache /c/api hay /c/auth.
// Cần HTTPS (hoặc localhost). Trang HTTP-IP bỏ qua êm. Khi đăng xuất, xoá cache tạm (CLEAR_CACHES).
export function registerSW() {
  if (!("serviceWorker" in navigator) || import.meta.env.DEV) return;
  if (!window.isSecureContext) return;
  addEventListener("load", () => {
    navigator.serviceWorker.register("/c/sw.js", { scope: "/c/" }).then((reg) => {
      reg.addEventListener("updatefound", () => {
        const w = reg.installing;
        w?.addEventListener("statechange", () => {
          if (w.state === "installed" && navigator.serviceWorker.controller) w.postMessage({ type: "SKIP_WAITING" });
        });
      });
    }).catch(() => { /* không hỗ trợ: bỏ qua */ });
  });
}

export function clearSwCaches() {
  try { navigator.serviceWorker?.controller?.postMessage({ type: "CLEAR_CACHES" }); } catch { /* bỏ qua */ }
}
