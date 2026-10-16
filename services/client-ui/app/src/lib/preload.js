// Bộ nạp trang (code-split) dùng chung: App dùng lazy(), thanh điều hướng gọi preload() khi rê chuột/chạm để mở trang tức thì.
export const LOADERS = {
  "/hom-nay": () => import("../pages/Today"),
  "/tong-quan": () => import("../pages/Dashboard"),
  "/vi-the": () => import("../pages/Positions"),
  "/rui-ro": () => import("../pages/Risk"),
  "/nhat-ky": () => import("../pages/Journal"),
  "/thi-truong": () => import("../pages/Market"),
  "/tin-lich": () => import("../pages/NewsCalendar"),
  "/tin-hieu": () => import("../pages/Signals"),
  "/kich-ban": () => import("../pages/Scenarios"),
  "/ai-trading": () => import("../pages/AiTrading"),
  "/chuyen-gia": () => import("../pages/Experts"),
  "/canh-bao": () => import("../pages/Alerts"),
  "/ho-so": () => import("../pages/Profile"),
  "/danh-muc": () => import("../pages/Portfolio"),
  "/ban-tin": () => import("../pages/Briefing"),
  "/thong-bao": () => import("../pages/Notifications"),
  "/gioi-han": () => import("../pages/Limits"),
  "/bao-cao": () => import("../pages/Reports"),
  "/tro-giup": () => import("../pages/Help"),
};
const done = new Set();
export function preload(path) {
  if (done.has(path) || !LOADERS[path]) return;
  done.add(path);
  LOADERS[path]().catch(() => done.delete(path));
  if (path === "/thi-truong") import("../components/chart/ProChart").catch(() => {});
}
