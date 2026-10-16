// Ảnh mẫu lưới ví dụ + thẻ kết quả test (dữ liệu GIẢ). Chạy qua run_examples_testcard.sh (build harness bằng vite trong docker).
import { chromium } from "playwright";
import fs from "node:fs";
const BASE = process.env.BASE || "http://127.0.0.1:4173", OUT = process.env.OUT || "out"; fs.mkdirSync(OUT, { recursive: true });
const SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 100"><rect width="160" height="100" fill="#1d2430"/>' + Array.from({ length: 24 }, (_, i) => { const y = 60 - i * 1.2 + Math.sin(i) * 12, u = i % 3 ? "#3fb68b" : "#e5604d"; return `<line x1="${8 + i * 6}" x2="${8 + i * 6}" y1="${y - 9}" y2="${y + 9}" stroke="${u}"/><rect x="${6 + i * 6}" y="${y - 4}" width="4" height="8" fill="${u}"/>`; }).join("") + "</svg>";
const b = await chromium.launch(), errs = [];
for (const [w, h] of [[375, 800], [768, 900], [1366, 900], [1920, 1000]]) for (const th of ["dark", "light"]) for (const [view, extra] of [["grid", ""], ["card", ""], ["card", "&pos=1"], ["grid", "&empty=1"]]) for (const lang of (w === 1366 ? ["vi", "en"] : ["vi"])) {
  const cx = await b.newContext({ viewport: { width: w, height: h } }); await cx.route("**/media/ex*", (r) => r.fulfill({ status: 200, contentType: "image/svg+xml", body: SVG })); const p = await cx.newPage();
  p.on("pageerror", (e) => errs.push(String(e).slice(0, 160)));
  await p.goto(`${BASE}/index.html?view=${view}&theme=${th}&lang=${lang}${extra}`); await p.waitForTimeout(400);
  if (view === "card") { await p.click("text=/Mở test khoá|Open locked/"); }
  const ov = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  const small = await p.evaluate(() => [...document.querySelectorAll("button,a.btn,input")].filter((e) => e.offsetParent && e.getBoundingClientRect().height < 38).length);
  if (ov > 0) errs.push(`TRÀN ${w} ${view}${extra} ${th} +${ov}`); if (small) errs.push(`CHẠM<38 ${small} ${w} ${view}${extra}`);
  if (view === "grid" && !extra) { await p.keyboard.press("Tab"); await p.keyboard.press("d"); await p.keyboard.press("ArrowRight"); await p.keyboard.press("s"); }
  await p.screenshot({ path: `${OUT}/xt-${view}${extra.replace(/\W/g, "")}-${w}-${th}-${lang}.png`, fullPage: true }); await p.context().close();
}
await b.close(); console.log(errs.length ? errs.join("\n") : "OK"); process.exit(errs.length ? 1 : 0);
