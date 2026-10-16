// Đo thời gian tải trang (Playwright/Chromium) qua nginx web-ui với phiên QA (cookie). Chạy bởi run_pageload.sh trên VPS.
// Mỗi vòng: COLD (context mới = cache trình duyệt rỗng) và WARM (cùng context, điều hướng lại). Báo cáo trung vị N vòng.
// Chỉ số: TTFB, FCP, LCP, DOMContentLoaded, load, networkidle, số request, byte truyền (transferSize), số request từ cache trình duyệt, request /api (số lượng, tổng thời gian chờ).
import { chromium } from 'playwright';
import fs from 'node:fs';

const BASE = process.env.BASE || 'http://web-ui:8080';
const COOKIE = (process.env.COOKIE || '').split('=');
const N = parseInt(process.env.N || '5');
const PAGES = (process.env.PAGES || '/,/#/suc-manh-tien-te,/#/ban-do-nhiet,/#/nhip-thi-truong').split(',');
const OUT = process.env.OUT || '/out';
const LABEL = process.env.LABEL || 'run';
const med = (a) => (a.length ? [...a].sort((x, y) => x - y)[Math.floor(a.length / 2)] : null);

const INIT = `
  window.__m = { lcp: 0, fcp: 0 };
  new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__m.lcp = e.startTime; }).observe({ type: 'largest-contentful-paint', buffered: true });
  new PerformanceObserver((l) => { for (const e of l.getEntries()) if (e.name === 'first-contentful-paint') window.__m.fcp = e.startTime; }).observe({ type: 'paint', buffered: true });
`;

async function visit(page, url, reload = false) {
  const t0 = Date.now();
  if (reload) await page.reload({ waitUntil: 'load', timeout: 90000 });
  else await page.goto(url, { waitUntil: 'load', timeout: 90000 });
  await page.waitForTimeout(4000);   // để các truy vấn API của trang hoàn tất (networkidle không dùng được: WebSocket/polling)
  const wall = Date.now() - t0;
  const m = await page.evaluate(() => {
    const nav = performance.getEntriesByType('navigation')[0] || {};
    const res = performance.getEntriesByType('resource');
    const api = res.filter((r) => r.name.includes('/api/v1/'));
    return {
      ttfb: nav.responseStart, dcl: nav.domContentLoadedEventEnd, load: nav.loadEventEnd, fcp: window.__m.fcp, lcp: window.__m.lcp,
      reqs: res.length + 1, bytes: res.reduce((s, r) => s + (r.transferSize || 0), 0) + (nav.transferSize || 0),
      cached: res.filter((r) => r.transferSize === 0 && r.decodedBodySize > 0).length,
      api_n: api.length, api_wait_ms: api.reduce((s, r) => s + (r.responseStart - r.requestStart), 0), api_max_ms: Math.max(0, ...api.map((r) => r.responseEnd - r.startTime)),
    };
  });
  return { ...m, idle: wall };
}

const browser = await chromium.launch();
const out = {};
for (const path of PAGES) {
  const runs = { cold: [], warm: [] };
  for (let i = 0; i < N; i++) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await ctx.addCookies([{ name: COOKIE[0], value: COOKIE.slice(1).join('='), url: BASE }]);
    await ctx.addInitScript(INIT);
    const page = await ctx.newPage();
    runs.cold.push(await visit(page, BASE + path));
    runs.warm.push(await visit(page, BASE + path, true));
    await ctx.close();
  }
  out[path] = {};
  for (const k of ['cold', 'warm']) {
    out[path][k] = Object.fromEntries(Object.keys(runs[k][0]).map((f) => [f, Math.round(med(runs[k].map((r) => r[f])) * 10) / 10]));
  }
  console.log(path, JSON.stringify(out[path]));
}
await browser.close();
fs.mkdirSync(OUT, { recursive: true });
fs.writeFileSync(`${OUT}/pageload_${LABEL}.json`, JSON.stringify(out, null, 1));
