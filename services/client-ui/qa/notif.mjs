// QA trực quan: Trung tâm thông báo, Cảnh báo (form), Giới hạn. Chạy trong container tạm trên VPS: sh qa/run.sh notif.mjs  (biến ONLY, THEMES, LANGS, VIEWS)
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = process.env.BASE || "http://127.0.0.1:8581/c/";
const OUT = process.env.OUT || "out";
const VIEWS_ALL = [["375x812", 375, 812, true], ["414x896", 414, 896, true], ["768x1024", 768, 1024, true], ["1366x768", 1366, 768, false]];
const VIEWS = process.env.VIEWS ? VIEWS_ALL.filter((v) => process.env.VIEWS.split(",").includes(v[0])) : VIEWS_ALL;
const THEMES = (process.env.THEMES || "dark,light").split(",");
const LANGS = (process.env.LANGS || "vi,en").split(",");
fs.mkdirSync(OUT, { recursive: true });

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
  await page.waitForSelector('[role="status"][aria-label="Đang tải"], [role="status"][aria-label="Loading"]', { state: "detached", timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(700);
};

const report = [];
const browser = await chromium.launch();
for (const lang of LANGS) {
  for (const [vname, w, h, mobile] of VIEWS) {
    for (const theme of THEMES) {
      const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: mobile ? 2 : 1, isMobile: mobile, hasTouch: mobile, colorScheme: theme, locale: lang === "en" ? "en-GB" : "vi-VN", timezoneId: "Asia/Ho_Chi_Minh" });
      const page = await ctx.newPage();
      const errs = []; let cur = "login";
      page.on("console", (m) => { if (m.type() === "error") errs.push(m.text().slice(0, 200)); });
      page.on("pageerror", (e) => errs.push(`[${cur}] pageerror: ${e.message}`.slice(0, 300)));
      const sfx = lang === "en" ? "-en" : "";
      const shot = async (name, full = true) => page.screenshot({ path: `${OUT}/${vname}-${theme}-${name}${sfx}.jpg`, type: "jpeg", quality: 70, fullPage: full });
      const check = async (name) => { const issues = await page.evaluate(AUDIT); report.push({ view: vname, theme, lang, page: name, issues }); };
      const go = async (hash) => { cur = hash; await page.evaluate((x) => { location.hash = x; }, hash); await page.waitForTimeout(300); await waitIdle(page); };
      const ONLY = process.env.ONLY ? process.env.ONLY.split(",") : null;
      const want = (n) => !ONLY || ONLY.includes(n);

      await page.goto(`${BASE}?mock=1`);
      await page.evaluate(([t, l]) => { try { localStorage.setItem("tc-theme", t); localStorage.setItem("tc-prefs", JSON.stringify({ theme: t, lang: l, onboarded: true })); } catch {} }, [theme, lang]);
      await page.reload();
      await page.waitForSelector("form");
      await page.fill('input[autocomplete="username"]', "12345678");
      await page.fill('input[autocomplete="current-password"]', "demo-cong-1");
      await page.click('button[type="submit"]');
      await page.waitForSelector("main#main-content", { timeout: 15000 });

      if (want("thong-bao")) { await go("#/thong-bao"); await shot("thong-bao"); await check("thong-bao"); }
      if (want("thong-bao-more")) {
        await go("#/thong-bao");
        const more = page.locator("main button", { hasText: lang === "en" ? "Load more" : "Xem thêm" });
        if (await more.count()) { await more.first().click(); await page.waitForTimeout(500); await shot("thong-bao-more"); await check("thong-bao-more"); }
      }
      if (want("thong-bao-cai-dat")) { await go("#/thong-bao?tab=settings"); await shot("thong-bao-cai-dat"); await check("thong-bao-cai-dat"); }
      if (want("thong-bao-lich-su")) { await go("#/thong-bao?tab=history"); await shot("thong-bao-lich-su"); await check("thong-bao-lich-su"); }
      if (want("canh-bao")) { await go("#/canh-bao"); await shot("canh-bao"); await check("canh-bao"); }
      if (want("canh-bao-form")) {
        await go("#/canh-bao");
        await page.locator("main button.btn.primary").first().click(); await page.waitForSelector('[role="dialog"]'); await page.waitForTimeout(300);
        await page.fill('[role="dialog"] input[inputmode="decimal"]', "1.1"); // mức giá
        await page.locator('[role="dialog"] button', { hasText: lang === "en" ? "Check now" : "Kiểm tra ngay" }).click({ timeout: 4000 }).catch((e) => errs.push("preview: " + e.message.slice(0, 80))); await page.waitForTimeout(700);
        await page.evaluate(() => document.querySelector('[role="dialog"]')?.scrollTo(0, 0));
        await page.screenshot({ path: `${OUT}/${vname}-${theme}-canh-bao-form-top${sfx}.jpg`, type: "jpeg", quality: 70 }); await check("canh-bao-form");
        await page.evaluate(() => document.querySelector('[role="dialog"]')?.scrollTo(0, 99999)); await page.waitForTimeout(200);
        await page.screenshot({ path: `${OUT}/${vname}-${theme}-canh-bao-form-bottom${sfx}.jpg`, type: "jpeg", quality: 70 });
        // lỗi xác thực: xoá giá trị rồi gửi
        await page.fill('[role="dialog"] input[inputmode="decimal"]', "");
        await page.locator('[role="dialog"] button[type="submit"]').click(); await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/${vname}-${theme}-canh-bao-form-loi${sfx}.jpg`, type: "jpeg", quality: 70 });
        await page.keyboard.press("Escape");
      }
      if (want("gioi-han")) { await go("#/gioi-han"); await shot("gioi-han"); await check("gioi-han"); }
      if (want("gioi-han-sheet")) {
        await go("#/gioi-han");
        await page.locator('main button[aria-label^="' + (lang === "en" ? "Edit: Maximum daily loss" : "Sửa: Lỗ tối đa trong ngày") + '"]').first().click(); await page.waitForSelector('[role="dialog"]');
        await page.fill('[role="dialog"] input', "5"); await page.waitForTimeout(250);
        await page.screenshot({ path: `${OUT}/${vname}-${theme}-gioi-han-noi-long${sfx}.jpg`, type: "jpeg", quality: 70 }); await check("gioi-han-sheet");
        await page.keyboard.press("Escape");
      }
      report.push({ view: vname, theme, lang, page: "_console", issues: errs.map((d) => ({ k: "console", d })) });
      await ctx.close();
    }
  }
}
await browser.close();
fs.writeFileSync(`${OUT}/report.json`, JSON.stringify(report, null, 1));
const bad = report.filter((r) => r.issues.length);
console.log(`Trang kiểm tra: ${report.length}; có vấn đề: ${bad.length}`);
for (const r of bad) { console.log(`\n## ${r.lang} ${r.view} ${r.theme} ${r.page}`); const seen = new Set(); for (const i of r.issues) { const k = i.k + i.d; if (seen.has(k)) continue; seen.add(k); console.log(`  - ${i.k}: ${i.d}`); } }
