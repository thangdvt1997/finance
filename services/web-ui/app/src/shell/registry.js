// Đăng ký trang tự động: mọi `pages/*.jsx` có `export const meta` (hoặc nằm trong LEGACY) trở thành 1 trang.
// meta: { path, label, group, icon, roles?: ["master"|"client"], order?, short?, primary?, keywords?, hidden? }
// Metadata đọc ĐỒNG BỘ qua plugin vite-plugin-ts-meta (không kéo cả trang vào bundle chính); component nạp lười qua import.meta.glob.
import { lazy } from "react";
import { LayoutDashboard } from "lucide-react";
import pageMeta from "virtual:ts-meta/pages";
import { LEGACY } from "./legacyPages";

const loaders = import.meta.glob("../pages/*.jsx");
export const GROUP_ORDER = ["Terminal", "Thị trường", "Thông tin", "Tài khoản", "Quản trị đội", "Vận hành"];
export const DEFAULT_PATH = "terminal";

const built = [];
for (const [p, load] of Object.entries(loaders)) {
  const name = p.replace(/^.*\//, "").replace(/\.jsx$/, "");
  const m = LEGACY[name] || pageMeta[name];
  if (!m || !m.path || m.hidden) continue;
  built.push({
    id: m.path, name, label: m.label || m.path, group: m.group || "Khác", short: m.short, icon: m.icon || LayoutDashboard,
    roles: m.roles || ["master"], perm: m.perm || "", order: m.order ?? 100, primary: !!m.primary, keywords: m.keywords || "",
    el: lazy(load),
  });
}
const gi = (g) => { const i = GROUP_ORDER.indexOf(g); return i < 0 ? GROUP_ORDER.length : i; };
export const ALL_ROUTES = built.sort((a, b) => gi(a.group) - gi(b.group) || a.order - b.order || a.label.localeCompare(b.label, "vi"));

/** Danh sách trang cho vai trò `role` (mặc định master). Client chỉ thấy trang khai báo roles gồm "client".
 *  Vai trò phụ (support|analyst|auditor): ngoài `roles`, trang có `perm` (vd "fleet.read") chỉ hiện khi `perms` của /auth/me có quyền đó (master luôn đủ). Chỉ để ẩn menu — server vẫn kiểm quyền thật. */
export const routesFor = (role, perms) => ALL_ROUTES.filter((r) => r.roles.includes(role || "master") && (!r.perm || !role || role === "master" || !perms || perms.includes("*") || perms.includes(r.perm)));
export const groupsOf = (routes) => [...new Set(routes.map((r) => r.group))];

// Lệnh Ctrl-K của Terminal: nạp lười, không chặn khởi động.
if (typeof window !== "undefined") {
  const run = () => import("../terminal/commands").then((m) => m.registerTerminalCommands()).catch(() => {});
  if ("requestIdleCallback" in window) requestIdleCallback(run, { timeout: 3000 }); else setTimeout(run, 1200);
}
