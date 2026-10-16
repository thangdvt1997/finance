// QA đa ngôn ngữ + đồng bộ cài đặt (chạy qua qa/run.sh i18n.mjs trên VPS). Mock (?mock=1).
//  - chụp các trang của Agent C ở vi và en (375/768/1366, tối + sáng ở 375), kiểm tra tràn ngang, nút/tiêu đề bị cắt, chữ Việt sót khi ở en
//  - kiểm thử đồng bộ prefs: đổi ngôn ngữ ở Hồ sơ -> máy chủ giả có lang=en -> xoá localStorage -> tải lại -> áp dụng; thử 409 và 404
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = process.env.BASE || "http://127.0.0.1:8581/c/";
const OUT = process.env.OUT || "out";
const LANGS = (process.env.LANGS || "vi,en").split(",");
const VIEWS = [["375x812", 375, 812, true, ["dark", "light"]], ["768x1024", 768, 1024, true, ["dark"]], ["1366x768", 1366, 768, false, ["dark"]]];
const PAGES = (process.env.PAGES || "ho-so,nhat-ky,thi-truong,tin-lich,tin-hieu,ban-tin,vi-the,rui-ro,tro-giup").split(",");
fs.mkdirSync(OUT, { recursive: true });

const AUDIT = () => {
  const vw = document.documentElement.clientWidth, issues = [];
  const vis = (el) => { const r = el.getBoundingClientRect(), cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none"; };
  const desc = (el) => `${el.tagName.toLowerCase()}${el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".") : ""} "${(el.getAttribute("aria-label") || el.textContent || "").trim().slice(0, 40)}"`;
  if (document.documentElement.scrollWidth > vw + 1) issues.push({ k: "page-overflow-x", d: `${document.documentElement.scrollWidth} > ${vw}` });
  const inScroller = (el) => { for (let p = el.parentElement; p; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if ((o === "auto" || o === "scroll") && p.scrollWidth > p.clientWidth) return true; } return false; };
  for (const el of document.querySelectorAll("main *")) {
    if (!vis(el) || inScroller(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.right > vw + 1 || r.left < -1) { issues.push({ k: "out-of-viewport", d: desc(el) }); if (issues.length > 10) break; }
  }
  // nút/tiêu đề bị cắt cứng (chữ rộng hơn hộp mà KHÔNG có ellipsis/wrap): overflow hidden + scrollWidth > clientWidth + không text-overflow
  for (const el of document.querySelectorAll("main button, main h1, main h2, main .btn, main .chip, main [role=tab], .bottom-nav *, header *")) {
    if (!vis(el) || el.children.length > 3) continue;
    const cs = getComputedStyle(el);
    if (el.scrollWidth > el.clientWidth + 2 && cs.textOverflow !== "ellipsis" && (cs.overflowX === "hidden" || cs.overflowX === "clip")) issues.push({ k: "clipped-text", d: desc(el) });
  }
  return issues.slice(0, 30);
};
// chữ Việt còn sót khi đang ở en (bỏ vùng dữ liệu máy chủ giả: tin, bản tin, ghi chú)
const VI_LEFT = () => {
  const VI = /[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ]/;
  const out = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const n = walker.currentNode, s = n.nodeValue.trim();
    if (!s || !VI.test(s)) continue;
    if (n.parentElement.closest("[data-server-text], script, style")) continue;
    out.add(s.slice(0, 70));
  }
  for (const el of document.querySelectorAll("[aria-label],[title],[placeholder]")) for (const a of ["aria-label", "title", "placeholder"]) { const v = el.getAttribute(a); if (v && VI.test(v)) out.add(`@${a}: ${v.slice(0, 60)}`); }
  return [...out].slice(0, 40);
};

const login = async (page) => {
  await page.fill('input[autocomplete="username"]', "12345678");
  await page.fill('input[autocomplete="current-password"]', "demo-cong-1");
  await page.click('button[type="submit"]');
  await page.waitForSelector("main#main-content", { timeout: 15000 });
};
const idle = async (page) => { await page.waitForTimeout(900); };
const report = [], viLeft = {}, errs = [];
const browser = await chromium.launch();

for (const lang of LANGS) for (const [vname, w, h, mobile, themes] of VIEWS) for (const theme of themes) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: mobile ? 2 : 1, isMobile: mobile, hasTouch: mobile, colorScheme: theme, locale: lang === "en" ? "en-GB" : "vi-VN", timezoneId: "Asia/Ho_Chi_Minh" });
  const page = await ctx.newPage();
  let cur = "login";
  page.on("pageerror", (e) => errs.push(`[${lang} ${vname} ${cur}] ${e.message}`.slice(0, 240)));
  page.on("console", (m) => { if (m.type() === "error") errs.push(`[${lang} ${vname} ${cur}] console: ${m.text()}`.slice(0, 240)); });
  const shot = (name) => page.screenshot({ path: `${OUT}/${vname}-${theme}-${lang}-${name}.jpg`, type: "jpeg", quality: 70, fullPage: true });
  const check = async (name) => {
    report.push({ lang, view: vname, theme, page: name, issues: await page.evaluate(AUDIT) });
    if (lang === "en") viLeft[`${vname}/${theme}/${name}`] = await page.evaluate(VI_LEFT);
  };
  await page.goto(`${BASE}?mock=1&mockprefs=off`);
  await page.evaluate(([t, l]) => { try { localStorage.clear(); localStorage.setItem("tc-prefs", JSON.stringify({ theme: t, lang: l, onboarded: true })); } catch {} }, [theme, lang]);
  await page.reload();
  await page.waitForSelector("form");
  await page.waitForTimeout(300);
  await shot("login"); await check("login");
  await login(page);
  for (const p of PAGES) {
    cur = p;
    await page.evaluate((x) => { location.hash = `#/${x}`; }, p);
    await idle(page);
    await shot(p); await check(p);
  }
  await ctx.close();
}

// ---- Đồng bộ prefs (mock) ----
const sync = [];
{
  const ctx = await browser.newContext({ viewport: { width: 414, height: 896 }, isMobile: true, hasTouch: true });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errs.push(`[sync] ${e.message}`.slice(0, 240)));
  await page.goto(`${BASE}?mock=1&mockprefs=off`);
  await page.evaluate(() => { localStorage.clear(); localStorage.setItem("tc-prefs", JSON.stringify({ onboarded: true })); });
  await page.reload(); await page.waitForSelector("form"); await login(page);
  await page.evaluate(() => { location.hash = "#/ho-so"; }); await idle(page);
  // đổi sang English bằng nút trong Hồ sơ
  await page.click('button[aria-pressed]:has-text("English")'); await page.waitForTimeout(2600);
  const srv = await page.evaluate(() => JSON.parse(localStorage.getItem("tc-mock-prefs") || "null"));
  sync.push(["PUT sau khi đổi ngôn ngữ", srv?.data?.lang === "en", JSON.stringify(srv)]);
  const h1 = await page.evaluate(() => document.documentElement.lang + "|" + (document.querySelector("h1")?.textContent || ""));
  sync.push(["giao diện đổi ngay sang en", h1.startsWith("en|"), h1]);
  // "thiết bị mới": xoá cài đặt cục bộ nhưng giữ máy chủ giả + phiên
  await page.evaluate(() => { localStorage.removeItem("tc-prefs"); localStorage.removeItem("tc-prefsync"); });
  await page.reload(); await page.waitForTimeout(2500);
  const l2 = await page.evaluate(() => document.documentElement.lang + "|" + JSON.stringify(JSON.parse(localStorage.getItem("tc-prefs") || "{}").lang));
  sync.push(["thiết bị mới kéo lang=en từ máy chủ", l2.startsWith("en|"), l2]);
  await shot_(page, "sync-en");
  await page.evaluate(() => { const p = JSON.parse(localStorage.getItem("tc-prefs") || "{}"); p.onboarded = true; localStorage.setItem("tc-prefs", JSON.stringify(p)); }); // bỏ qua hướng dẫn đầu tiên
  // 409: đổi mật độ trong lúc "thiết bị khác" vừa ghi
  await page.goto(`${BASE}?mock=1&mockprefs=409#/ho-so`); await page.waitForTimeout(1500);
  await page.click('button[aria-pressed]:has-text("Dark")').catch(() => {});
  await page.waitForTimeout(4500);
  const s409 = await page.evaluate(() => JSON.parse(localStorage.getItem("tc-mock-prefs") || "null"));
  sync.push(["409: trộn + thử lại thành công (theme=dark, density=compact từ máy khác)", s409?.data?.theme === "dark" && s409?.data?.density === "compact" && s409?.data?.lang === "en", JSON.stringify({ theme: s409?.data?.theme, density: s409?.data?.density, lang: s409?.data?.lang, rev: s409?.rev })]);
  // 404: backend chưa có -> im lặng
  await page.goto(`${BASE}?mock=1&mockprefs=404#/ho-so`); await page.waitForTimeout(2500);
  const note = await page.evaluate(() => [...document.querySelectorAll('[role="status"]')].map((e) => e.textContent).join(" | "));
  sync.push(["404: chạy im lặng, hiện 'chưa khả dụng'", /not available yet|chưa khả dụng/i.test(note), note.slice(0, 160)]);
  await ctx.close();
}
async function shot_(page, n) { await page.screenshot({ path: `${OUT}/sync-${n}.jpg`, type: "jpeg", quality: 70 }); }
await browser.close();

fs.writeFileSync(`${OUT}/report.json`, JSON.stringify({ report, viLeft, sync, errs }, null, 1));
const bad = report.filter((r) => r.issues.length);
console.log(`Trang: ${report.length}; có vấn đề bố cục: ${bad.length}`);
for (const r of bad) { console.log(`\n## ${r.lang} ${r.view} ${r.theme} ${r.page}`); const seen = new Set(); for (const i of r.issues) { const k = i.k + i.d; if (!seen.has(k)) { seen.add(k); console.log(`  - ${i.k}: ${i.d}`); } } }
console.log("\n== chữ Việt còn sót khi ở en ==");
for (const [k, v] of Object.entries(viLeft)) if (v.length) { console.log(`# ${k}`); for (const s of v) console.log(`   ${s}`); }
console.log("\n== đồng bộ prefs ==");
for (const [n, ok, d] of sync) console.log(`${ok ? "OK  " : "FAIL"} ${n}${ok ? "" : "  -> " + d}`);
console.log(`\nlỗi console/page: ${errs.length}`); for (const e of [...new Set(errs)].slice(0, 15)) console.log("  " + e);
