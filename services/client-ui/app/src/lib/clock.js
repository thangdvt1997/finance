// Đồng hồ dùng chung: MỘT setInterval duy nhất cho mọi huy hiệu độ trễ (chỉ chạy khi còn component đăng ký).
import { useSyncExternalStore } from "react";

const TICK_MS = 2000;
let now = Date.now();
let timer = null;
const subs = new Set();

function start() {
  if (timer) return;
  now = Date.now();
  timer = setInterval(() => {
    now = Date.now();
    subs.forEach((f) => f());
  }, TICK_MS);
}
function subscribe(fn) {
  subs.add(fn);
  start();
  return () => {
    subs.delete(fn);
    if (!subs.size && timer) {
      clearInterval(timer);
      timer = null;
    }
  };
}
const snap = () => now;

/** Thời điểm hiện tại (ms), làm mới mỗi 2 giây; mọi component dùng chung một timer. */
export function useClock() {
  return useSyncExternalStore(subscribe, snap);
}
