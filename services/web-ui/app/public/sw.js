/* Service worker AN TOÀN cho dữ liệu tài chính.
 * Chỉ cache: tài nguyên tĩnh có hash (/assets/*), shell HTML, manifest, icon.
 * KHÔNG BAO GIỜ cache/chặn: /api/*, WebSocket, non-GET, request có Authorization/Range, khác origin,
 * phản hồi không phải 200 (401/403/5xx), phản hồi Cache-Control: no-store/private hoặc có Set-Cookie.
 * Cập nhật: bản mới ở trạng thái "waiting" cho tới khi UI gửi {type:"SKIP_WAITING"} (nút "Tải lại"). */
const VERSION = "v1";
const STATIC = "ts-static-" + VERSION;
const SHELL = "ts-shell-" + VERSION;
const SHELL_KEY = "/__shell";
const PRECACHE = ["/manifest.webmanifest", "/favicon.svg", "/theme-init.js", "/icons/icon-192.png", "/icons/icon-512.png", "/icons/apple-touch-icon.png"];

/** Chỉ phản hồi tĩnh, công khai, thành công mới được lưu. */
function cacheable(res) {
  if (!res || res.status !== 200 || res.type !== "basic") return false;
  const cc = (res.headers.get("cache-control") || "").toLowerCase();
  if (cc.includes("no-store") || cc.includes("private")) return false;
  if (res.headers.has("set-cookie") || res.headers.has("www-authenticate")) return false;
  return true;
}

/** true nếu SW được phép xử lý request này (mặc định: KHÔNG). */
function handled(req, url) {
  if (req.method !== "GET") return false;
  if (url.origin !== self.location.origin) return false;
  if (req.headers.has("authorization") || req.headers.has("range")) return false;
  if (url.pathname === "/api" || url.pathname.startsWith("/api/")) return false;
  if (req.headers.get("upgrade")) return false;
  return true;
}
const isStaticPath = (p) => p.startsWith("/assets/") || p.startsWith("/icons/") || PRECACHE.includes(p);

self.addEventListener("install", (e) => {
  // Precache mềm: lỗi 1 file (hoặc 401 do auth) không làm hỏng cài đặt. KHÔNG skipWaiting tự động.
  e.waitUntil(
    caches.open(STATIC).then((c) =>
      Promise.allSettled(PRECACHE.map(async (u) => {
        const res = await fetch(u, { credentials: "same-origin", cache: "reload" });
        if (cacheable(res)) await c.put(u, res);
      })),
    ),
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k.startsWith("ts-") && k !== STATIC && k !== SHELL) await caches.delete(k);
    await self.clients.claim();
  })());
});

self.addEventListener("message", (e) => {
  const t = e.data && e.data.type;
  if (t === "SKIP_WAITING") self.skipWaiting();
  if (t === "CLEAR_CACHES") e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k.startsWith("ts-")).map((k) => caches.delete(k)))));
});

async function staleWhileRevalidate(req) {
  const c = await caches.open(STATIC);
  const hit = await c.match(req);
  const net = fetch(req).then((res) => {
    if (cacheable(res)) c.put(req, res.clone());
    return res;
  }).catch(() => null);
  if (hit) return hit;
  return (await net) || Response.error();
}

async function navigate(req) {
  try {
    const res = await fetch(req);
    // Chỉ lưu shell khi là HTML 200; 401/403 đi thẳng tới trình duyệt, không lưu, không thay bằng bản cũ.
    if (cacheable(res) && (res.headers.get("content-type") || "").includes("text/html")) {
      (await caches.open(SHELL)).put(SHELL_KEY, res.clone());
    }
    return res;
  } catch (err) {
    const shell = await (await caches.open(SHELL)).match(SHELL_KEY);
    return shell || new Response("<!doctype html><meta charset=utf-8><title>Mất kết nối</title><body style=\"font:16px system-ui;background:#090d13;color:#d6dfeb;padding:2rem\"><h1>Mất kết nối</h1><p>Không tải được ứng dụng. Kiểm tra mạng rồi tải lại trang.</p>", { status: 503, headers: { "content-type": "text/html; charset=utf-8" } });
  }
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (!handled(req, url)) return; // để trình duyệt tự xử lý
  if (req.mode === "navigate") { e.respondWith(navigate(req)); return; }
  if (isStaticPath(url.pathname)) e.respondWith(staleWhileRevalidate(req));
});
