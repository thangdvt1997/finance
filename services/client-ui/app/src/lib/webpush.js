// Web Push (tự host, VAPID): đăng ký/huỷ thiết bị này với máy chủ. Máy chủ chỉ lưu đăng ký của CHÍNH người dùng đăng nhập (xem docs/CLIENT_PLATFORM.md).
// Nội dung push là thông báo CHUNG (không số dư/tên tài khoản); SW (`public/sw.js`) hiển thị và mở /c/#/thong-bao khi bấm.
import { api, apiWrite } from "./api";

export const webPushSupported = () => typeof window !== "undefined" && window.isSecureContext && "serviceWorker" in navigator && "PushManager" in window && typeof Notification !== "undefined";

const keyBytes = (b64u) => { const p = "=".repeat((4 - (b64u.length % 4)) % 4); const s = atob((b64u + p).replace(/-/g, "+").replace(/_/g, "/")); return Uint8Array.from(s, (c) => c.charCodeAt(0)); };

/** {enabled, public_key, subscriptions} từ máy chủ, hoặc null khi không dùng được (chưa bật/lỗi/chế độ mẫu). */
export async function webPushInfo(signal) {
  try { const r = await api("/user/push", {}, signal); return r && r.enabled && r.public_key ? r : null; } catch { return null; }
}

export async function currentSubscription() {
  try { const reg = await navigator.serviceWorker.ready; return await reg.pushManager.getSubscription(); } catch { return null; }
}

export async function enableWebPush(publicKey) {
  if (!webPushSupported()) throw new Error("Thiết bị này không hỗ trợ thông báo đẩy.");
  const perm = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
  if (perm !== "granted") throw new Error("Bạn chưa cho phép thông báo trong trình duyệt.");
  const reg = await navigator.serviceWorker.ready;
  let sub = await reg.pushManager.getSubscription();
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(publicKey) });
  const j = sub.toJSON();
  await apiWrite("POST", "/user/push/subscribe", { endpoint: j.endpoint, keys: { p256dh: j.keys?.p256dh, auth: j.keys?.auth }, user_agent: navigator.userAgent.slice(0, 200) });
  return sub;
}

export async function disableWebPush() {
  const sub = await currentSubscription();
  if (!sub) return;
  try { await apiWrite("POST", "/user/push/unsubscribe", { endpoint: sub.endpoint }); } catch { /* vẫn huỷ ở thiết bị */ }
  try { await sub.unsubscribe(); } catch { /* bỏ qua */ }
}

export const testWebPush = () => apiWrite("POST", "/user/push/test", {});
