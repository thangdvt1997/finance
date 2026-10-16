// Kho nhỏ trên localStorage: mọi thao tác bọc try/catch (chế độ ẩn danh/đầy bộ nhớ không làm hỏng giao diện).
const subs = new Set();
/** Đăng ký nghe mọi lần ghi (key) để đồng bộ nền (lib/prefsync.jsx). Trả hàm huỷ. */
export function onLocalWrite(fn) { subs.add(fn); return () => subs.delete(fn); }
export function lget(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw == null ? fallback : JSON.parse(raw);
  } catch { return fallback; }
}
export function lset(key, value) {
  let ok = false;
  try { localStorage.setItem(key, JSON.stringify(value)); ok = true; } catch { /* bỏ qua */ }
  if (subs.size) for (const f of subs) { try { f(key); } catch { /* bỏ qua */ } }
  return ok;
}
export function ldel(key) {
  try { localStorage.removeItem(key); } catch { /* bỏ qua */ }
}
