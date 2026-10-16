// QA trang "Kịch bản" (client-ui) ở chế độ mẫu ?mock=1: 375 + 1366, tối/sáng, vi/en. Chạy: QA_W=<thư mục tạm> sh qa/run.sh scenarios.mjs
// Kiểm: tràn ngang, phần tử ra ngoài khung, lỗi JS, chữ Việt sót khi en, tên nguồn dữ liệu, có thẻ/ảnh/biểu đồ.
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = process.env.BASE || "http://127.0.0.1:8581/c/";
const OUT = process.env.OUT || "out";
fs.mkdirSync(OUT, { recursive: true });
const VIEWS = [["m375", 375, 812, true], ["d1366", 1366, 768, false]];
const BANNED = /dukascopy|yahoo|binance|reuters|myfxbook|okx|kucoin|bybit|stooq|frankfurter|https?:\/\//i;
const AUDIT = () => {
  const vw = document.documentElement.clientWidth, out = [];
  if (document.documentElement.scrollWidth > vw + 1) out.push(`overflow-x ${document.documentElement.scrollWidth}>${vw}`);
  const inScroller = (el) => { for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if (o === "auto" || o === "scroll" || o === "hidden") return true; } return false; };
  for (const el of document.querySelectorAll("main *")) {
    const r = el.getBoundingClientRect();
    if (!r.width || inScroller(el)) continue;
    if (r.right > vw + 1 || r.left < -1) { out.push(`out ${el.tagName.toLowerCase()}.${String(el.className).slice(0, 40)}`); if (out.length > 8) break; }
  }
  return out;
};
const VI_LEFT = () => {
  const VI = /[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ]/, out = new Set();
  const w = document.createTreeWalker(document.querySelector("main") || document.body, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) { const n = w.currentNode, s = n.nodeValue.trim(); if (s && VI.test(s) && !n.parentElement.closest("[data-server-text]")) out.add(s.slice(0, 70)); }
  for (const el of document.querySelectorAll("main [aria-label], main [title]")) for (const a of ["aria-label", "title"]) { const v = el.getAttribute(a); if (v && VI.test(v)) out.add(`@${a}: ${v.slice(0, 60)}`); }
  return [...out].slice(0, 20);
};

const browser = await chromium.launch();
const errs = [], rep = [];
for (const lang of ["vi", "en"]) for (const theme of ["dark", "light"]) for (const [vn, w, h, mobile] of VIEWS) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, isMobile: mobile, hasTouch: mobile, colorScheme: theme, timezoneId: "Asia/Ho_Chi_Minh" });
  const page = await ctx.newPage();
  page.setDefaultTimeout(12000);
  let cur = "login";
  page.on("pageerror", (e) => errs.push(`[${lang} ${theme} ${vn} ${cur}] ${e.message}`.slice(0, 220)));
  page.on("console", (m) => { if (m.type() === "error") errs.push(`[${lang} ${theme} ${vn} ${cur}] console ${m.text()}`.slice(0, 220)); });
  await page.goto(`${BASE}?mock=1`);
  await page.evaluate(([t, l]) => { localStorage.clear(); localStorage.setItem("tc-prefs", JSON.stringify({ theme: t, lang: l, onboarded: true })); }, [theme, lang]);
  await page.reload();
  await page.fill('input[autocomplete="username"]', "12345678");
  await page.fill('input[autocomplete="current-password"]', "demo-cong-1");
  await page.click('button[type="submit"]');
  await page.waitForSelector("main#main-content", { timeout: 15000 });
  const tag = `${vn}-${theme}-${lang}`;
  const step = async (name, hash, after) => {
    cur = name;
    if (hash) await page.evaluate((x) => { location.hash = x; }, hash);
    await page.waitForTimeout(1300);
    if (after) await after();
    await page.screenshot({ path: `${OUT}/sc-${tag}-${name}.jpg`, type: "jpeg", quality: 72, fullPage: true });
    const a = await page.evaluate(([au, vl, bn]) => {
      const AU = new Function(`return (${au})`)(), VL = new Function(`return (${vl})`)();
      const txt = document.querySelector("main")?.innerText || "";
      return { audit: AU(), viLeft: VL(), banned: new RegExp(bn, "i").test(txt), cards: document.querySelectorAll(".sc-card").length, imgs: [...document.querySelectorAll("main img")].filter((i) => i.complete && i.naturalWidth > 0).length,
        canvas: document.querySelectorAll("main canvas").length, banner: /không phải khuyến nghị|not investment advice/i.test(txt), alerts: [...document.querySelectorAll("main [role=alert]")].map((x) => x.innerText.slice(0, 80)) };
    }, [AUDIT.toString(), VI_LEFT.toString(), BANNED.source]);
    if (lang === "vi") delete a.viLeft;
    rep.push({ tag, name, ...a });
  };
  await step("live", "#/kich-ban");
  await step("history", "#/kich-ban?tab=history");
  await step("library", "#/kich-ban?tab=library");
  await step("about", "#/kich-ban?tab=about");
  await step("detail", "#/kich-ban", async () => { await page.click(".sc-card >> nth=0"); await page.waitForTimeout(1500); });
  if (theme === "dark") await step("zoom", null, async () => { await page.click(".sc-big"); await page.waitForTimeout(500); });
  await ctx.close();
}
for (const r of rep) console.log(JSON.stringify(r));
console.log("ERRORS", errs.length, JSON.stringify(errs.slice(0, 12)));
await browser.close();
