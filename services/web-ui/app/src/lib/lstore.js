// Kho nhỏ trên localStorage: mọi thao tác bọc try/catch (chế độ ẩn danh/đầy bộ nhớ không làm hỏng giao diện).
export function lget(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw == null ? fallback : JSON.parse(raw);
  } catch { return fallback; }
}
export function lset(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch { return false; }
}
export function ldel(key) {
  try { localStorage.removeItem(key); } catch { /* bỏ qua */ }
}
