// D2: kiểm tra theme mặc định / ghi đè / bền qua reload (không đặt ts-theme thủ công)
import { chromium } from "playwright";
const BASE = process.env.BASE || "http://127.0.0.1:8580";
const b = await chromium.launch();
for (const scheme of ["dark", "light"]) {
  const ctx = await b.newContext({ viewport: { width: 1366, height: 768 }, colorScheme: scheme, baseURL: BASE });
  await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: process.env.QA_USER, secret: process.env.QA_PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } });
  const p = await ctx.newPage();
  const th = async () => p.evaluate(() => [document.documentElement.dataset.theme, localStorage.getItem("ts-theme"), (JSON.parse(localStorage.getItem("ts-ux") || "{}")).theme].join("/"));
  p.on("response", async (r) => { if (/user\/prefs/.test(r.url())) console.log(r.request().method(), r.status(), (await r.text().catch(()=>"")).slice(0,400)); });
  await p.goto(`${BASE}/#/thi-truong/EURUSD?tf=H1`, { waitUntil: "load" }); await p.waitForTimeout(3000);
  console.log(scheme, "first", await th());
  await p.reload({ waitUntil: "load" }); await p.waitForTimeout(3000);
  console.log(scheme, "reload", await th());
  await ctx.close();
}
await b.close();
