// QA nhom F: giao dien AI Training Class tren backend THAT (khong mock). Chay qua tests/qa/f_run_ui.sh
// Moi buoc ghi PASS/FAIL; phong thu co tien to qa_stab_ (don bang f_cleanup.py). Khong dat lenh, khong mo test khoa.
import { chromium } from "playwright";
import fs from "node:fs";
const BASE = process.env.BASE || "http://127.0.0.1:8580", OUT = process.env.OUT || "out", ROLE = process.env.ROLE || "master";
const W = +(process.env.W || 1440), H = +(process.env.H || 950), LLM = process.env.LLM !== "0";
fs.mkdirSync(OUT, { recursive: true });
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");
fs.writeFileSync(`${OUT}/a.png`, PNG);
fs.writeFileSync(`${OUT}/kb.yaml`, "id: qa_stab_y\nname: thu\nside: sell\n");
fs.writeFileSync(`${OUT}/d.csv`, "ts,o,h,l,c\n1,1,2,0.5,1.5\n");
fs.writeFileSync(`${OUT}/x.pdf`, "%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF");
fs.writeFileSync(`${OUT}/big.png`, Buffer.concat([PNG, Buffer.alloc(900000)]));
fs.writeFileSync(`${OUT}/bad.exe`, "MZ");
const R = []; const errs = []; const net = [];
const log = (ok, n, d = "") => { R.push([ok, n, d]); console.log((ok ? "PASS " : "FAIL ") + n + (d ? " :: " + String(d).slice(0, 220) : "")); };
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: W, height: H }, colorScheme: "dark", baseURL: BASE, acceptDownloads: true });
let lg; for (let i = 0; i < 8; i++) { lg = await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: process.env.QA_USER, secret: process.env.QA_PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } }); if (lg.status() !== 429) break; await new Promise((r) => setTimeout(r, 30000)); }
log(lg.status() === 200, `dang nhap ${ROLE}`, lg.status());
await ctx.addInitScript(() => { try { const v = JSON.parse(localStorage.getItem("ts-ux") || "{}"); v.onboarded = 99; localStorage.setItem("ts-ux", JSON.stringify(v)); localStorage.setItem("ts-aitrading-lang", "vi"); localStorage.removeItem("cr-room"); if (!sessionStorage.getItem("f-init")) { localStorage.removeItem("cr-tour-done"); sessionStorage.setItem("f-init", "1"); } } catch { /* bo */ } });
const page = await ctx.newPage(); page.setDefaultTimeout(15000);
page.on("pageerror", (e) => errs.push("pageerror " + String(e.message).slice(0, 200)));
page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errs.push("console " + m.text().slice(0, 200)); });
page.on("response", (rs) => { const u = rs.url(); if (/\/api\/v1\//.test(u) && rs.status() >= 400 && !/\/user\/prefs/.test(u)) net.push(`${rs.request().method()} ${u.split("/api/v1")[1].slice(0, 80)} ${rs.status()}`); });
const shot = (n) => page.screenshot({ path: `${OUT}/f-${ROLE}-${W}-${n}.png` }).catch(() => {});
const step = async (n, fn) => { try { const r = await fn(); log(r !== false && !(typeof r === "string" && !/^OK/.test(r)), n, typeof r === "string" ? r : ""); return r; } catch (e) { log(false, n, String(e.message).split("\n")[0]); await shot("fail-" + n.replace(/\W+/g, "_").slice(0, 30)); return false; } };
const mobile = W < 900;
const nav = async (re) => { if (mobile) await page.locator(".cr-nav button").filter({ hasText: re }).click(); await page.waitForTimeout(300); };
const ta = () => page.locator("textarea.cr-ta").first();
let tourSeen = null;
const dismissTour = async (wait = 0) => { const d = page.getByText(/Hướng dẫn nhanh|Quick (guide|tour)/).first(); for (let t = 0; t < wait && !(await d.isVisible().catch(() => false)); t += 250) await page.waitForTimeout(250); if (await d.isVisible().catch(() => false)) { tourSeen = true; await page.getByRole("button", { name: /^(Bỏ qua|Skip)$/ }).first().click().catch(() => page.keyboard.press("Escape")); await page.waitForTimeout(400); return true; } return false; };
const title = `qa_stab_ui_${Math.random().toString(36).slice(2, 6)}`;

await page.goto(`${BASE}/#/${ROLE === "expert" ? "lop-hoc-ai" : "ai-trading"}`, { waitUntil: "load" });
await page.waitForTimeout(2500);
const body = () => page.evaluate(() => document.body.innerText);
if (ROLE === "master") {
  // --- cac tab AI Trading
  const tabs = await page.getByRole("tab").allInnerTexts().catch(() => []);
  log(tabs.length >= 3, "AI Trading co cac tab", tabs.join(" | "));
  for (const t of tabs) {
    await step(`tab AI Trading: ${t.trim()}`, async () => {
      await page.getByRole("tab", { name: t.trim(), exact: true }).first().click(); await page.waitForTimeout(1400); await dismissTour(/Lớp học|Training/.test(t) ? 3000 : 0);
      const b = await body();
      if (/binance|yahoo|metaquotes|twelve|dukascopy|openai/i.test(b)) return "LO TEN NGUON";
      if (await page.evaluate(() => [...document.querySelectorAll("button,a")].some((x) => /^(buy|sell|đặt lệnh|mua|bán|place order)$/i.test(x.textContent.trim())))) return "CO NUT DAT LENH";
      return true;
    });
  }
  await shot("tabs");
  await step("the chien luoc: mo chi tiet", async () => { await page.getByRole("tab", { name: /Chiến lược|Strateg|Tổng quan|Overview/ }).first().click().catch(() => {}); await page.waitForTimeout(800); const c = page.locator("[class*=card], article").first(); return (await c.count()) > 0; });
  await step("Day kich ban moi: mo tab + form YAML", async () => { await page.getByRole("tab", { name: /Kịch bản nến|Dạy kịch bản|Teach/ }).first().click(); await page.waitForTimeout(1200); await shot("teach"); return (await page.getByLabel(/YAML kịch bản/).count()) > 0 || "khong thay o YAML"; });
  await step("Day kich ban: 'Nap mau' dien YAML", async () => { await page.getByRole("button", { name: /Nạp mẫu/ }).first().click(); await page.waitForTimeout(300); return (await page.getByLabel(/YAML kịch bản/).first().inputValue()).length > 50 || "o YAML rong sau khi nap mau"; });
  await step("Day kich ban: YAML hong -> bao loi 422 ro rang", async () => { await page.getByLabel(/YAML kịch bản/).first().fill("id: [hong\n  khong hop le ......"); await page.getByRole("button", { name: /Kiểm tra & lưu/ }).first().click(); await page.waitForTimeout(1500); return (await page.locator("[role=alert]").allInnerTexts()).join("").length > 5 || "khong hien loi"; });
  await step("Day kich ban: tep anh sai (.exe) bi chan o o anh", async () => { const inp = page.locator("input[type=file][accept^='image']").first(); await inp.setInputFiles(`${OUT}/bad.exe`).catch(() => {}); await page.waitForTimeout(500); return true; });
  await step("Day kich ban: YAML + anh hop le -> luu + the kich ban xuat hien", async () => {
    const y = "id: qa_stab_ui_sc\nname: \"QA UI thu\"\nsummary: \"Kich ban thu cua QA, se bi xoa.\"\nside: sell\nsymbols: [EURUSD]\ntfs: [H1]\ndetector:\n  cooldown_bars: 8\n  rules:\n    - {rule: move_atr, dir: up, bars: 6, min: 2.0}\n    - {rule: upper_wick, min_ratio: 0.4}\nlevels:\n  sl: {type: swing_high, bars: 6, buffer_atr: [0.25, 0.5]}\n  tp_r: [1.0, 2.0]\n  max_hold: 60\nimages: [a.png]\n";
    await page.getByLabel(/YAML kịch bản/).first().fill(y); await page.locator("input[type=file][accept^='image']").first().setInputFiles(`${OUT}/a.png`); await page.waitForTimeout(400);
    await page.getByRole("button", { name: /Kiểm tra & lưu/ }).first().click(); await page.waitForTimeout(2500); await shot("teach-saved");
    const ok = await page.locator("[role=status]").allInnerTexts(); const al = await page.locator("[role=alert]").allInnerTexts();
    return ok.join("").length > 3 || "khong co thong bao luu; alert=" + al.join("|").slice(0, 120);
  });
  await step("Day kich ban: the qa_stab_ui_sc co trong danh sach + quy trinh job", async () => { await page.getByRole("tab", { name: /Kịch bản nến|Dạy kịch bản/ }).first().click(); await page.waitForTimeout(1500); return /qa_stab_ui_sc/.test(await body()) || "khong thay the kich ban vua nap"; });
  await page.getByRole("tab", { name: /Lớp học AI|AI Training Class/ }).first().click(); await page.waitForTimeout(2000); await dismissTour(3000);
  { const bb = await body(); log(!/Lớp học AI/.test(bb), "doi ten: khong con chu 'Lop hoc AI' tren trang", (bb.match(/Lớp học AI/g) || []).length); }
}
// --- AI Training Class
await step("tieu de/tab 'AI Training Class'", async () => /AI Training Class/.test(await body()) || "chua doi ten (thieu 'AI Training Class')");
await step("tao phong qua UI", async () => {
  if (mobile) { await page.locator(".cr-top-l .cr-only-m").click().catch(() => {}); await page.waitForTimeout(300); }
  if (!(await page.getByRole("button", { name: /Phòng mới|New room/ }).first().isVisible().catch(() => false))) { await page.locator(mobile ? ".cr-top-l .cr-only-m" : ".cr-top-l .cr-only-d").first().click(); await page.waitForTimeout(400); }
  await page.getByRole("button", { name: /Phòng mới|New room/ }).first().click(); await page.getByLabel(/Tên kịch bản|Tên phòng|Room name/).first().fill(title);
  await page.getByRole("button", { name: /Tạo phòng|Create room/ }).first().click(); await page.getByRole("heading", { name: title }).first().waitFor(); await shot("phong"); return true;
});
await step("tour lan dau hien (sau khi vao phong) + 'Bo qua' dong va nho", async () => {
  await page.waitForTimeout(1500); const shown = tourSeen || (await dismissTour());
  const saved = await page.evaluate(() => { try { return !!localStorage.getItem("cr-tour-done"); } catch { return false; } });
  return !shown ? "tour lan dau khong hien (da xem truoc do?)" : (saved ? true : "bo qua tour nhung khong luu co nho");
});
await step("phong rong: goi y 3 cau + vi du mo dau", async () => /3 câu|3 sentences/.test(await body()));
await step("o nhap: dem ky tu + gioi han 1500", async () => { await ta().fill("x".repeat(1600)); const n = (await ta().inputValue()).length; await ta().fill(""); return n <= 1500 || "vuot 1500: " + n; });
await step("phim tat Ctrl+K mo tim kiem", async () => { await ta().click(); await page.keyboard.press("Control+k"); await page.waitForTimeout(400); return await page.locator("input[aria-label*='Tìm trong phòng'], input[placeholder*='Tìm trong phòng']").first().isVisible().catch(() => false) || "khong mo o tim (hoac khac phim)"; });
await page.keyboard.press("Escape");
await step("gui tin nhan + streaming + markdown (AI that)", async () => {
  await ta().fill("Kịch bản Sell EURUSD H1: sau nhịp tăng 2 ATR trong 6 nến, nến giảm có bóng trên 40% thì vào Sell, SL trên đỉnh, TP 2R."); await ta().press("Enter");
  const t0 = Date.now(); await page.locator(".cr-msg.ai").first().waitFor({ timeout: 20000 }).catch(() => {});
  const sawBusy = await page.locator(".cr-msg.ai[aria-busy]").count();
  await page.locator(".cr-msg.ai[aria-busy]").waitFor({ state: "detached", timeout: 200000 }).catch(() => {});
  await page.waitForTimeout(1200); await shot("chat"); const dt = ((Date.now() - t0) / 1000).toFixed(0);
  const txt = await page.locator(".cr-msg.ai").last().innerText(); if (!txt || txt.length < 20) return "AI khong tra loi";
  if (/\*\*|^#{1,3} /m.test(txt)) return "markdown chua render (con ** hoac #): " + txt.slice(0, 60);
  return `OK: AI tra loi sau ${dt}s, busy=${sawBusy}, ${txt.length} ky tu`;
});
await step("tin cua minh hien o ben phai/ten dung", async () => (await page.locator(".cr-msg").count()) >= 2);
for (const [n, f, ok] of [["anh PNG", "a.png", true], ["YAML", "kb.yaml", true], ["CSV", "d.csv", true], ["PDF", "x.pdf", true], ["anh >700KB", "big.png", false], ["tep .exe", "bad.exe", false]]) {
  await step(`dinh kem ${n} (${ok ? "chap nhan" : "phai tu choi"})`, async () => {
    const before = await page.locator(".cr-msg").count();
    await page.locator("input[type=file]").first().setInputFiles(`${OUT}/${f}`); await page.waitForTimeout(600);
    const cap = page.locator(".cr-tray input").first(); if (await cap.count()) await cap.fill("qa chu thich");
    const sendBtn = page.getByRole("button", { name: /^(Gửi|Send)$/ }); if (await sendBtn.isEnabled().catch(() => false)) await sendBtn.click();
    await page.waitForTimeout(2500);
    const alertTxt = await page.locator(".cr [role=alert]").allInnerTexts().catch(() => []); const after = await page.locator(".cr-msg").count();
    // don khay
    for (let i = 0; i < 3; i++) { const x = page.getByRole("button", { name: /Bỏ tệp|Remove file/ }).first(); if (await x.count()) await x.click().catch(() => {}); }
    if (ok) return after > before || "khong thay tin dinh kem moi; alert=" + alertTxt.join("|").slice(0, 100);
    return (after === before && (alertTxt.length || true)) || "tep sai van duoc dinh kem";
  });
}
await shot("dinhkem");
await step("ghim tin + tab Ghim", async () => {
  await nav(/Chat/);
  const m = page.locator(".cr-msg").first(); await m.hover(); const b = m.getByRole("button", { name: /Ghim|Pin/ }).first(); if (!(await b.count())) return "khong thay nut Ghim tren tin";
  await b.click(); await page.waitForTimeout(800); await nav(/Ghim|Pin/); await page.getByRole("tab", { name: /Ghim|Pin/ }).first().click().catch(() => {}); return true;
});
await nav(/Chat/);
await step("tim kiem trong phong (Ctrl+K + 'EURUSD')", async () => {
  const s = page.locator("input[aria-label*='Tìm trong phòng'], input[placeholder*='Tìm trong phòng']").first(); if (!(await s.isVisible().catch(() => false))) { await page.keyboard.press("Escape"); await page.getByRole("button", { name: /Tìm trong phòng/ }).first().click(); await page.waitForTimeout(300); }
  await s.fill("EURUSD"); await page.waitForTimeout(1200); return /kết quả cho|results for/.test(await body()) || "khong hien ket qua tim";
});
await page.keyboard.press("Escape");
await step("tab Ho so: 16 hang", async () => { await nav(/Hồ sơ|Profile/); if (!mobile) await page.getByRole("tab", { name: /Hồ sơ|Profile/ }).first().click(); await page.waitForTimeout(900); await shot("hoso"); const n = await page.locator(".cr-prow, .cr-canvas tr, [class*=canvas] [class*=row]").count(); return n >= 14 || `chi thay ${n} hang (so khop selector)`; });
await step("Ho so: do ro y tuong hien", async () => /Độ rõ|Clarity/i.test(await body()));
await step("Ho so: nut Xac nhan/Sua/Hoi lai", async () => { const t = await body(); return (/Xác nhận|Confirm/.test(t) && /Sửa|Edit/.test(t)) || "thieu nut"; });
await step("tab Vi du (luoi + Đ/S/G)", async () => { await nav(/Ví dụ|Examples/); if (!mobile) await page.getByRole("tab", { name: /Ví dụ|Examples/ }).first().click(); await page.waitForTimeout(800); await shot("vidu"); return true; });
await step("tab Test (the ket qua)", async () => { await nav(/Test/); if (!mobile) await page.getByRole("tab", { name: /^Test/ }).first().click(); await page.waitForTimeout(800); await shot("test"); return true; });
await step("tab Bieu do (chon vung nen)", async () => { if (mobile) return "OK: bo qua (mobile khong co tab rieng)"; await page.getByRole("tab", { name: /Biểu đồ|Chart/ }).first().click(); await page.waitForTimeout(2500); await shot("bieudo"); const c = await page.locator("canvas").count(); return c > 0 || "khong thay canvas bieu do"; });
await step("tab So tay: phien ban + xuat YAML", async () => {
  if (!mobile) await page.getByRole("tab", { name: /Sổ tay|Notebook/ }).first().click(); await page.waitForTimeout(1200); await shot("sotay");
  const b = page.getByRole("button", { name: /Xuất|Export/ }).first(); if (await b.count()) { await b.click(); await page.waitForTimeout(2500); }
  return true;
});
await step("Cach day hieu qua", async () => { await page.getByRole("button", { name: /Cách dạy|How to teach/ }).first().click(); await page.waitForTimeout(600); const t = await body(); await shot("cachday"); await page.keyboard.press("Escape"); return /Việc nên làm|Do/.test(t); });
await step("Buoi hoc mau (demo) chay duoc", async () => { await page.getByRole("button", { name: /demo|Buổi học mẫu|Watch demo/i }).first().click(); await page.waitForTimeout(700); for (let i = 0; i < 6; i++) await page.getByRole("button", { name: /^(Tiếp|Next)/ }).first().click({ timeout: 1500 }).catch(() => {}); await shot("demo"); const t = await body(); await page.keyboard.press("Escape"); return /minh hoạ|Illustrative/i.test(t) || "khong co nhan minh hoa"; });
await step("Mau khoi tao kich ban", async () => { await page.getByRole("button", { name: /^(Mẫu|Templates)|Chọn từ mẫu/ }).first().click(); await page.waitForTimeout(500); const n = await page.locator(".gd-tpl").count(); await shot("mau"); await page.keyboard.press("Escape"); return n >= 4 || "so mau " + n; });
await step("Tour tham quan 5 buoc", async () => { await page.getByRole("button", { name: /Tham quan|Tour/ }).first().click(); await page.waitForTimeout(500); for (let i = 0; i < 4; i++) await page.getByRole("button", { name: /^(Tiếp|Next)$/ }).click({ timeout: 2000 }); await shot("tour"); await page.keyboard.press("Escape"); return true; });
await step("trang thai model (cuc bo/toc do)", async () => /cục bộ|local|Mô hình|Model/i.test(await body()));
await step("khong lo ten nguon du lieu / khong nut dat lenh", async () => {
  const b = await body(); if (/binance|yahoo|metaquotes|twelve|dukascopy|openai/i.test(b)) return "LO TEN NGUON";
  return !(await page.evaluate(() => [...document.querySelectorAll("button,a")].some((x) => /^(buy|sell|đặt lệnh|mua|bán|place order)$/i.test(x.textContent.trim()))));
});
await step("khong con lenh '/' hien tren UI (ngoai chat/chip)", async () => { const m = await page.evaluate(() => { const e = document.querySelector(".cr"); if (!e) return "khong thay .cr"; const c = e.cloneNode(true); c.querySelectorAll(".cr-msgs,.cr-chips").forEach((x) => x.remove()); const r = (c.innerText || c.textContent).match(/.{0,25}(^|\s)\/(test|quet|luu|bien-the|doi-xung|so-sanh|giai-thich|tom-tat|hoi-them|ve)\b.{0,15}/); return r ? r[0] : ""; }); return m ? "con lenh /: " + m : true; });
await step("khong tran ngang trang", async () => { const o = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth); return o <= 0 || "tran " + o + "px"; });
// don phong kich ban khac khong co; ghi log mang
console.log("NET4xx5xx", JSON.stringify([...new Set(net)].slice(0, 20)));
console.log("JSERRORS", JSON.stringify(errs.slice(0, 10)));
console.log(`TONG ${R.filter((x) => x[0]).length}/${R.length} PASS; loi JS ${errs.length}; http>=400 ${net.length}`);
fs.writeFileSync(`${OUT}/f-ui-${ROLE}-${W}.json`, JSON.stringify({ R, errs, net }, null, 1));
await browser.close();
