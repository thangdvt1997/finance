// Kiểm thử trực quan client-ui bằng Playwright (chạy TRONG container tạm trên VPS, KHÔNG chạy trên laptop):
//   docker run --rm --network host -v $PWD/qa:/qa -w /qa mcr.microsoft.com/playwright:v1.49.0-jammy sh -c "npm i --no-save --silent playwright@1.49.0 && node shots.mjs"
// Mặc định dùng chế độ dữ liệu mẫu (?mock=1). Với auth thật dùng e2e.mjs.
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = process.env.BASE || "http://127.0.0.1:8581/c/";
const OUT = process.env.OUT || "out";
const VIEWS = [["375x812", 375, 812, true], ["414x896", 414, 896, true], ["768x1024", 768, 1024, true], ["1366x768", 1366, 768, false]];
const THEMES = (process.env.THEMES || "dark,light").split(",");
const PAGES = ["tong-quan", "vi-the", "rui-ro", "nhat-ky", "thi-truong", "tin-lich", "tin-hieu", "canh-bao", "ho-so", "danh-muc", "ban-tin", "thong-bao", "tro-giup"];
const ONLY = process.env.ONLY ? process.env.ONLY.split(",") : null;
fs.mkdirSync(OUT, { recursive: true });

// Chạy trong trang: tìm lỗi bố cục
const AUDIT = () => {
  const vw = document.documentElement.clientWidth;
  const issues = [];
  const vis = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none"; };
  const desc = (el) => `${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}${el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/).slice(0, 3).join(".") : ""}${(el.getAttribute("aria-label") || el.textContent || "").trim().slice(0, 28) ? ` "${(el.getAttribute("aria-label") || el.textContent).trim().slice(0, 28)}"` : ""}`;
  // 1) tràn ngang trang
  if (document.documentElement.scrollWidth > vw + 1) issues.push({ k: "page-overflow-x", d: `scrollWidth ${document.documentElement.scrollWidth} > ${vw}` });
  // 2) phần tử vượt mép phải (bỏ qua nếu nằm trong vùng cuộn ngang có chủ đích)
  const inScroller = (el) => { for (let p = el.parentElement; p; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if ((o === "auto" || o === "scroll") && p.scrollWidth > p.clientWidth) return true; } return false; };
  for (const el of document.querySelectorAll("main *")) {
    if (!vis(el) || inScroller(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.right > vw + 1 || r.left < -1) { issues.push({ k: "out-of-viewport", d: `${desc(el)} [${Math.round(r.left)}..${Math.round(r.right)}] vw=${vw}` }); if (issues.length > 12) break; }
  }
  // 3) chồng panel: các .panel/.kpi/.pos-card anh em giao nhau
  const groups = new Map();
  for (const el of document.querySelectorAll("main .panel, main .kpi, main .pos-card")) { if (!vis(el)) continue; const p = el.parentElement; if (!groups.has(p)) groups.set(p, []); groups.get(p).push(el); }
  for (const [, els] of groups) for (let i = 0; i < els.length; i++) for (let j = i + 1; j < els.length; j++) {
    const a = els[i].getBoundingClientRect(), b = els[j].getBoundingClientRect();
    const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left), oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    if (ox > 2 && oy > 2) issues.push({ k: "overlap", d: `${desc(els[i])} x ${desc(els[j])} (${Math.round(ox)}x${Math.round(oy)})` });
  }
  // 4) mục tiêu chạm >= 44px (trừ liên kết nội dòng trong đoạn văn)
  for (const el of document.querySelectorAll("a,button,input:not([type=hidden]),select,textarea,[role=tab],[role=switch],[role=radio],summary")) {
    if (!vis(el) || el.closest(".sr-only") || el.classList.contains("skip") || el.id === "tv-attr-logo") continue;
    const cs = getComputedStyle(el); if (cs.display === "inline" && el.tagName === "A") continue;
    const r = el.getBoundingClientRect();
    if (Math.min(r.width, r.height) < 43.5) issues.push({ k: "touch<44", d: `${desc(el)} ${Math.round(r.width)}x${Math.round(r.height)}` });
  }
  // 5) văn bản bị cắt không có dấu ba chấm, chữ nhỏ < 11px
  for (const el of document.querySelectorAll("main p, main span, main div, main b, main li")) {
    if (!vis(el) || el.children.length) continue; const cs = getComputedStyle(el);
    if (parseFloat(cs.fontSize) < 10.5 && el.textContent.trim()) issues.push({ k: "tiny-font", d: `${desc(el)} ${cs.fontSize}` });
  }
  return issues.slice(0, 40);
};

const waitIdle = async (page) => {
  await page.waitForSelector('[role="status"][aria-label="Đang tải"]', { state: "detached", timeout: 15000 }).catch(() => {}); // (không dùng waitForFunction: CSP chặn eval)
  await page.waitForTimeout(650);
};

const report = [];
const browser = await chromium.launch();
for (const [vname, w, h, mobile] of VIEWS) {
  for (const theme of THEMES) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: mobile ? 2 : 1, isMobile: mobile, hasTouch: mobile, colorScheme: theme, locale: "vi-VN", timezoneId: "Asia/Ho_Chi_Minh" });
    const page = await ctx.newPage();
    const errs = []; let curPage = "login";
    page.on("console", (m) => { if (m.type() === "error") errs.push(m.text().slice(0, 200)); });
    page.on("pageerror", (e) => errs.push(`[${curPage}] pageerror: ${e.message} ${(e.stack || "").split(String.fromCharCode(10))[1] || ""}`.slice(0, 300)));
    const shot = async (name, full = true) => page.screenshot({ path: `${OUT}/${vname}-${theme}-${name}.jpg`, type: "jpeg", quality: 72, fullPage: full });
    const check = async (name) => { const issues = await page.evaluate(AUDIT); report.push({ view: vname, theme, page: name, issues }); };

    await page.goto(`${BASE}?mock=1`);
    await page.evaluate((t) => { document.documentElement.dataset.theme = t; try { localStorage.setItem("tc-theme", t); localStorage.setItem("tc-prefs", JSON.stringify({ theme: t, onboarded: true })); } catch {} }, theme);
    await page.reload();
    await page.waitForSelector("form");
    await page.waitForTimeout(300);
    if (!ONLY || ONLY.includes("login")) { await shot("login"); await check("login"); }
    // đăng nhập lỗi (trạng thái lỗi)
    if (!ONLY || ONLY.includes("login-error")) {
      await page.fill('input[autocomplete="username"]', "12345678");
      await page.fill('input[autocomplete="current-password"]', "sai-mat-khau");
      await page.click('button[type="submit"]');
      await page.waitForSelector('[role="alert"]');
      await shot("login-error"); await check("login-error");
    }
    // ghép cặp
    if (!ONLY || ONLY.includes("pair")) {
      await page.click('button:has-text("Ghép cặp lần đầu")');
      await page.waitForTimeout(250); await shot("pair"); await check("pair");
      await page.click('button:has-text("Đăng nhập")');
    }
    await page.fill('input[autocomplete="username"]', "12345678");
    await page.fill('input[autocomplete="current-password"]', "demo-cong-1");
    await page.click('button[type="submit"]');
    await page.waitForSelector("main#main-content", { timeout: 15000 });
    for (const p of PAGES) {
      if (ONLY && !ONLY.includes(p)) continue;
      curPage = p;
      await page.evaluate((x) => { location.hash = `#/${x}`; }, p);
      await page.waitForTimeout(300);
      await waitIdle(page);
      await shot(p); await check(p);
    }
    // sheet đổi tài khoản + menu Thêm + đổi trang nhật ký
    if (!ONLY || ONLY.includes("sheets")) {
      await page.evaluate(() => { location.hash = "#/tong-quan"; }); await waitIdle(page);
      await page.click('header button[aria-haspopup="dialog"]'); await page.waitForSelector('[role="dialog"]'); await page.waitForTimeout(300);
      await shot("sheet-accounts", false); await check("sheet-accounts");
      await page.keyboard.press("Escape");
      if (mobile && w < 1024) { await page.click('nav.bottom-nav button'); await page.waitForSelector('[role="dialog"]'); await page.waitForTimeout(300); await shot("sheet-more", false); await check("sheet-more"); await page.keyboard.press("Escape"); }
      // tài khoản MT4: EA mất kết nối
      await page.click('header button[aria-haspopup="dialog"]'); await page.waitForSelector('[role="dialog"]');
      await page.click('[role="dialog"] button.row:has-text("7654321")'); await waitIdle(page);
      await page.evaluate(() => { location.hash = "#/tong-quan"; }); await waitIdle(page);
      await shot("tong-quan-ea-off"); await check("tong-quan-ea-off");
    }
    report.push({ view: vname, theme, page: "_console", issues: errs.map((d) => ({ k: "console", d })) });
    await ctx.close();
  }
}
await browser.close();
fs.writeFileSync(`${OUT}/report.json`, JSON.stringify(report, null, 1));
const bad = report.filter((r) => r.issues.length);
console.log(`Trang kiểm tra: ${report.length}; có vấn đề: ${bad.length}`);
for (const r of bad) { console.log(`\n## ${r.view} ${r.theme} ${r.page}`); const seen = new Set(); for (const i of r.issues) { const k = i.k + i.d; if (seen.has(k)) continue; seen.add(k); console.log(`  - ${i.k}: ${i.d}`); } }
