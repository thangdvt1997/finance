// QA trang "Kịch bản" với API THẬT (không mock): đăng nhập bằng tài khoản thử (QA_USER/QA_PASS), 375 + 1366, sáng/tối, vi/en.
// Chạy: xem qa/run_scenarios_real.sh (tạo + xoá tài khoản thử).
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = process.env.BASE || "http://127.0.0.1:8581/c/";
const OUT = process.env.OUT || "out";
fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
const errs = [], rep = [];
let shapes = null;
for (const lang of ["vi", "en"]) for (const theme of ["dark", "light"]) for (const [vn, w, h, mobile] of [["m375", 375, 812, true], ["d1366", 1366, 768, false]]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile, colorScheme: theme, timezoneId: "Asia/Ho_Chi_Minh" });
  const page = await ctx.newPage();
  await page.goto(`${BASE}?mock=0&mockpat=0`);
  // đăng nhập/đổi mật khẩu bằng fetch trong trang (cookie phiên Secure chỉ đi qua trình duyệt)
  const post = (path, data) => page.evaluate(async ([u, d]) => { const x = await fetch(u, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(d) }); let j = {}; try { j = await x.json(); } catch {} return { st: x.status, j }; }, [`${BASE}auth/${path}`, data]);
  let lr = await post("login", { platform: "mt5", login: process.env.QA_USER, secret: process.env.QA_PASS });
  if (lr.st !== 200) { console.log("login fail", lr.st); process.exit(1); }
  if (lr.j.must_change_password) { // tài khoản thử mới: đổi mật khẩu một lần (ngẫu nhiên, chỉ trong bộ nhớ)
    const np = `Qa-${Math.random().toString(36).slice(2)}-${Date.now()}`;
    const cp = await post("change-password", { current_password: process.env.QA_PASS, new_password: np });
    if (cp.st >= 300) { console.log("change-password fail", cp.st); process.exit(1); }
    process.env.QA_PASS = np;
    lr = await post("login", { platform: "mt5", login: process.env.QA_USER, secret: np });
  }
  if (!shapes) {
    shapes = {};
    for (const p of ["patterns/live?view=active", "patterns/live?view=history", "patterns/trades?status=all", "patterns/stats", "patterns/examples", "patterns/spec"]) {
      shapes[p] = await page.evaluate(async (u) => { const x = await fetch(u, { credentials: "same-origin" }); let j = null; try { j = await x.json(); } catch {}
        return { st: x.status, keys: j && typeof j === "object" ? Object.keys(j).slice(0, 12) : null, n: Array.isArray(j?.items) ? j.items.length : undefined, first: Array.isArray(j?.items) && j.items[0] ? Object.keys(j.items[0]).slice(0, 30) : undefined, ex: Array.isArray(j?.items) && j.items[0] ? JSON.stringify(j.items[0]).slice(0, 300) : undefined }; }, `${BASE}api/v1/${p}`);
    }
    console.log("SHAPES", JSON.stringify(shapes));
  }
  page.setDefaultTimeout(12000);
  let cur = "";
  page.on("pageerror", (e) => errs.push(`[${lang} ${theme} ${vn} ${cur}] ${e.message}`.slice(0, 220)));
  page.on("console", (m) => { if (m.type() === "error") errs.push(`[${lang} ${theme} ${vn} ${cur}] console ${m.text()}`.slice(0, 220)); });
  // cài đặt đồng bộ máy chủ thắng ở thiết bị mới -> ghi lang/theme lên máy chủ (PUT client-prefs, có CSRF) rồi mới đặt localStorage
  await page.evaluate(async ([t, l, B]) => {
    const g = await (await fetch(`${B}api/v1/user/client-prefs`, { credentials: "same-origin" })).json().catch(() => null);
    const c = await (await fetch(`${B}api/v1/user/csrf`, { credentials: "same-origin" })).json().catch(() => null);
    if (g && c?.token) await fetch(`${B}api/v1/user/client-prefs`, { method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": c.token }, body: JSON.stringify({ rev: g.rev, data: { ...(g.data || {}), lang: l, theme: t } }) });
    localStorage.setItem("tc-prefs", JSON.stringify({ theme: t, lang: l, onboarded: true }));
  }, [theme, lang, BASE]);
  await page.reload();
  await page.waitForSelector("main#main-content", { timeout: 15000 });
  const tag = `${vn}-${theme}-${lang}`;
  const step = async (name, hash, after) => {
    cur = name;
    if (hash) await page.evaluate((x) => { location.hash = x; }, hash);
    await page.waitForTimeout(2500);
    if (after) await after();
    await page.screenshot({ path: `${OUT}/real-${tag}-${name}.jpg`, type: "jpeg", quality: 72, fullPage: true });
    rep.push({ tag, name, ...(await page.evaluate(() => {
      const t = document.querySelector("main")?.innerText || "";
      return { ox: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1, cards: document.querySelectorAll(".sc-card").length, imgs: [...document.querySelectorAll("main img")].filter((i) => i.complete && i.naturalWidth > 0).length,
        broken: [...document.querySelectorAll("main .sc-noimg")].length, canvas: document.querySelectorAll("main canvas").length, alerts: [...document.querySelectorAll("main [role=alert]")].map((x) => x.innerText.slice(0, 90)), banned: /dukascopy|yahoo|binance|reuters|stooq|https?:\/\//i.test(t) };
    })) });
  };
  await step("live", "#/kich-ban");
  await step("history", "#/kich-ban?tab=history");
  await step("library", "#/kich-ban?tab=library");
  await step("about", "#/kich-ban?tab=about");
  if (await page.$(".sc-card")) await step("detail", "#/kich-ban?tab=history", async () => { await page.waitForTimeout(800); const c = await page.$(".sc-card"); if (c) { await c.click(); await page.waitForTimeout(2500); } });
  await ctx.close();
}
for (const r of rep) console.log(JSON.stringify(r));
console.log("ERRORS", errs.length, JSON.stringify(errs.slice(0, 12)));
await browser.close();
