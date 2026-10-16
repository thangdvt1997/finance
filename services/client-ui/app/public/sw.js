/* Service worker AN TOÀN cho dữ liệu tài khoản. Phạm vi /c/.
 * Chỉ cache tài nguyên tĩnh có hash (/c/assets/*), icon, manifest, shell HTML.
 * KHÔNG BAO GIỜ cache/chặn: /c/api/*, /c/auth/*, non-GET, request có Authorization/Range, khác origin,
 * phản hồi không phải 200, phản hồi no-store/private hoặc có Set-Cookie. Dữ liệu tài khoản không bao giờ vào Cache Storage. */
const VERSION = "v2";
const STATIC = "tc-static-" + VERSION;
const SHELL = "tc-shell-" + VERSION;
const SHELL_KEY = "/c/__shell";
const PRECACHE = ["/c/manifest.webmanifest", "/c/favicon.svg", "/c/theme-init.js", "/c/icons/icon-192.png", "/c/icons/icon-512.png", "/c/icons/apple-touch-icon.png"];

function cacheable(res) {
  if (!res || res.status !== 200 || res.type !== "basic") return false;
  const cc = (res.headers.get("cache-control") || "").toLowerCase();
  if (cc.includes("no-store") || cc.includes("private")) return false;
  if (res.headers.has("set-cookie") || res.headers.has("www-authenticate")) return false;
  return true;
}
function handled(req, url) {
  if (req.method !== "GET") return false;
  if (url.origin !== self.location.origin) return false;
  if (req.headers.has("authorization") || req.headers.has("range")) return false;
  if (!url.pathname.startsWith("/c/")) return false;
  if (url.pathname.startsWith("/c/api/") || url.pathname.startsWith("/c/auth/")) return false;
  return true;
}
const isStaticPath = (p) => p.startsWith("/c/assets/") || p.startsWith("/c/icons/") || PRECACHE.includes(p);

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(STATIC).then((c) => Promise.allSettled(PRECACHE.map(async (u) => {
    const res = await fetch(u, { credentials: "same-origin", cache: "reload" });
    if (cacheable(res)) await c.put(u, res);
  }))));
});
self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k.startsWith("tc-") && k !== STATIC && k !== SHELL) await caches.delete(k);
    await self.clients.claim();
  })());
});
self.addEventListener("message", (e) => {
  const t = e.data && e.data.type;
  if (t === "SKIP_WAITING") self.skipWaiting();
  if (t === "CLEAR_CACHES") e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k.startsWith("tc-")).map((k) => caches.delete(k)))));
});
async function staleWhileRevalidate(req) {
  const c = await caches.open(STATIC);
  const hit = await c.match(req);
  const net = fetch(req).then((res) => { if (cacheable(res)) c.put(req, res.clone()); return res; }).catch(() => null);
  if (hit) return hit;
  return (await net) || Response.error();
}
async function navigate(req) {
  try {
    const res = await fetch(req);
    if (cacheable(res) && (res.headers.get("content-type") || "").includes("text/html")) (await caches.open(SHELL)).put(SHELL_KEY, res.clone());
    return res;
  } catch (err) {
    const shell = await (await caches.open(SHELL)).match(SHELL_KEY);
    return shell || new Response("<!doctype html><meta charset=utf-8><meta name=viewport content=\"width=device-width\"><title>Mất kết nối</title><body style=\"font:16px system-ui;background:#090d13;color:#d6dfeb;padding:2rem\"><h1>Mất kết nối</h1><p>Không tải được ứng dụng. Kiểm tra mạng rồi tải lại trang.</p>", { status: 503, headers: { "content-type": "text/html; charset=utf-8" } });
  }
}
self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (!handled(req, url)) return;
  if (req.mode === "navigate") { e.respondWith(navigate(req)); return; }
  if (isStaticPath(url.pathname)) e.respondWith(staleWhileRevalidate(req));
});

// ---- Thông báo: hiển thị push (nếu sau này có dịch vụ đẩy) và mở ứng dụng khi bấm. Payload là JSON ngắn {title, body, url}; không chứa số dư.
self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) { d = { title: "Thông báo", body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(String(d.title || "Thông báo").slice(0, 80), { body: String(d.body || "").slice(0, 200), icon: "/c/icons/icon-192.png", badge: "/c/icons/icon-192.png", data: { url: "/c/#/thong-bao" } }));
});
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = "/c/#/thong-bao";
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((cs) => {
    for (const c of cs) { if (c.url.indexOf("/c/") >= 0 && "focus" in c) { c.navigate(url).catch(() => {}); return c.focus(); } }
    return self.clients.openWindow(url);
  }));
});
