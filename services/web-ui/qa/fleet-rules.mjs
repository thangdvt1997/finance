// QA trực quan trang "Luật & tuân thủ" (#/luat). Chạy qua: sh qa/fleet-pw.sh fleet-rules.mjs rules
// Cần seed trước (tuỳ chọn, để có dữ liệu): sh /root/rules_seed.sh  (qa/fleet-rules-seed.sh); dọn: sh /root/rules_seed.sh clean
import { session, go, checks, fin, totpEnable, OUT } from "./fleet-lib.mjs";
const shot = async (s, name) => { const t = /light/.test(name) ? "light" : "dark"; await s.page.evaluate((t) => { document.documentElement.dataset.theme = t; }, t); await s.page.waitForTimeout(250); await s.page.screenshot({ path: `${OUT}/${name}.png` }); console.log("shot", name); };

async function run(theme, w, h, mobile, tag) {
  const s = await session({ theme, w, h, mobile });
  const p = s.page;
  await go(s, "luat", 2500);
  await shot(s, `rules-${tag}-compliance`);
  await checks(s, `${tag}/tuan-thu`);
  const txt = await p.evaluate(() => document.body.innerText);
  console.log(tag, "có banner disclaimer:", /KHÁC NHAU|khác nhau/i.test(txt), "| có RoNote:", /không có đặt lệnh/i.test(txt));
  // Mẫu luật
  await p.getByRole("tab", { name: /Mẫu luật/ }).click();
  await p.waitForTimeout(900);
  await shot(s, `rules-${tag}-templates`);
  // Mở trình soạn từ mẫu gợi ý
  await p.getByRole("button", { name: "Tạo mẫu luật" }).click().catch(() => {});
  await p.waitForTimeout(500);
  const sel = p.locator("select").first();
  if (await sel.count()) { await sel.selectOption({ index: 2 }).catch(() => {}); }
  await p.waitForTimeout(400);
  await shot(s, `rules-${tag}-editor`);
  // Kiểm tra hợp lệ phía client: xoá tên và đặt giá trị ngoài biên
  const name = p.getByLabel(/Tên mẫu/);
  await name.fill("");
  await p.locator("input.num").first().fill("500").catch(() => {});
  await p.getByRole("button", { name: /Lưu mẫu luật/ }).click();
  await p.waitForTimeout(400);
  const errs = await p.evaluate(() => [...document.querySelectorAll(".fl-err")].map((e) => e.textContent));
  console.log(tag, "lỗi hợp lệ client:", JSON.stringify(errs));
  await shot(s, `rules-${tag}-editor-err`);
  await p.getByRole("button", { name: "Huỷ" }).click();
  // Gán luật
  await p.getByRole("tab", { name: /Gán luật/ }).click();
  await p.waitForTimeout(700);
  await shot(s, `rules-${tag}-assignments`);
  await p.getByRole("button", { name: /Gán luật mới/ }).click();
  await p.waitForTimeout(900);
  await shot(s, `rules-${tag}-assign`);
  await checks(s, `${tag}/gan`);
  fin(s);
  await s.close();
}

// Luồng đầy đủ tạo -> gán -> xoá (desktop tối) để thử máy chủ thật
async function crud() {
  const s = await session({ theme: "dark" });
  const p = s.page;
  await go(s, "luat?tab=mau", 1200);
  let r = await s.req("POST", "/auth/admin/rules/templates", { name: "qa-fleet-crud", kind: "max_drawdown", params: { limit_pct: 9, mode: "static" }, description: "" });
  if (r.status === 403) { await totpEnable(s); r = await s.req("POST", "/auth/admin/rules/templates", { name: "qa-fleet-crud", kind: "max_drawdown", params: { limit_pct: 9, mode: "static" }, description: "" }); }
  console.log("tạo mẫu qua API:", r.status);
  await go(s, "luat?tab=mau", 2000);
  await shot(s, "rules-crud-templates");
  await p.getByRole("button", { name: /Xoá mẫu qa-fleet-crud/ }).click();
  await p.waitForTimeout(500);
  await shot(s, "rules-crud-delete-confirm");
  await p.getByRole("button", { name: "Xoá mẫu", exact: true }).click();
  await p.waitForTimeout(1200);
  console.log("còn mẫu qa-fleet-crud:", await p.getByText("qa-fleet-crud").count());
  fin(s);
  await s.close();
}

if (process.env.ONLY !== "crud") {
await run("dark", 1366, 800, false, "dark-1366");
await run("light", 1366, 800, false, "light-1366");
await run("dark", 390, 844, true, "dark-390");
await run("light", 390, 844, true, "light-390");
}
await crud();
