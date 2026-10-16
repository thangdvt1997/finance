import { session, go } from "./fleet-lib.mjs";
const s = await session({ w: 390, h: 844, mobile: true });
const p = s.page;
const info = (sel) => p.evaluate((sel) => {
  const out = [];
  for (const e of document.querySelectorAll(sel)) {
    const r = e.getBoundingClientRect();
    if (r.width && r.right > 392) {
      let a = e.parentElement, clipped = false;
      while (a && a !== document.body) { const cs = getComputedStyle(a); if (/(hidden|auto|scroll|clip)/.test(cs.overflowX) && a.getBoundingClientRect().right <= 392) { clipped = true; break; } a = a.parentElement; }
      if (!clipped) out.push(`${e.tagName}.${String(e.className).slice(0, 40)} r=${Math.round(r.right)} w=${Math.round(r.width)}`);
    }
  }
  return [innerWidth, out.slice(0, 8)];
}, sel);
for (const h of ["luat", "luat?tab=mau", "luat?tab=gan"]) { await go(s, h, 1800); console.log(h, JSON.stringify(await info(".fl-page, .fl-page *"))); }
await s.close();
