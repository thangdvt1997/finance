// Kiểm tra i18n (chạy trên VPS):  node scripts/i18n-check.cjs [lọc-đường-dẫn] [--fail] [--vi]
//  - mặc định: liệt kê khoá t("...") chưa có bản dịch en trong src/i18n/en/*.js
//  - --vi: liệt kê thêm chuỗi tiếng Việt CÒN SÓT (chuỗi/JSX có dấu tiếng Việt nằm ngoài t()) để bọc nốt
//  - lọc-đường-dẫn: chỉ xét tệp có đường dẫn chứa chuỗi này (vd pages/Market)
const fs = require("fs"), path = require("path");
const root = path.join(__dirname, "..", "app", "src");
const args = process.argv.slice(2);
const filter = args.find((a) => !a.startsWith("--"));
const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]));
const files = walk(root);
const SEP = path.sep;
const en = new Set(), seen = new Map(), conflicts = [];
const unq = (q, raw) => { try { return q === '"' ? JSON.parse('"' + raw + '"') : raw.replace(/\\(['\\])/g, "$1"); } catch { return raw; } };
for (const f of files.filter((f) => f.includes(`${SEP}i18n${SEP}en${SEP}`))) {
  const s = fs.readFileSync(f, "utf8");
  for (const m of s.matchAll(/"((?:[^"\\]|\\.)*)"\s*:/g)) en.add(unq('"', m[1]));
  try { // phát hiện khoá trùng giữa các tệp mà bản dịch KHÁC nhau (tệp nạp sau ghi đè tệp trước)
    const o = new Function(s.replace(/export\s+default/, "return"))();
    for (const [k, v] of Object.entries(o)) { const prev = seen.get(k); if (prev && prev.v !== v && !path.basename(f).startsWith("zz_")) conflicts.push(`${k}\n    ${prev.f}: ${prev.v}\n    ${path.basename(f)}: ${v}`); seen.set(k, { v, f: path.basename(f) }); }
  } catch (e) { console.log(`LỖI cú pháp từ điển ${path.basename(f)}: ${e.message}`); }
}
if (conflicts.length) { console.log(`CẢNH BÁO ${conflicts.length} khoá trùng giữa các tệp en với bản dịch khác nhau:`); for (const c of conflicts) console.log("  " + c); }
const src = files.filter((f) => /\.(jsx?|mjs)$/.test(f) && !f.includes(`${SEP}i18n${SEP}`) && (!filter || f.replace(/\\/g, "/").includes(filter)));
const miss = new Map();
const noComments = (txt) => txt.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " ")).split("\n").map((l) => l.replace(/(^|[^:"'`])\/\/.*$/, "$1")).join("\n");
for (const f of src) {
  if (/lib.i18n\.js$/.test(f)) continue;
  const s = noComments(fs.readFileSync(f, "utf8"));
  for (const m of s.matchAll(/\b(?:t|tr|tn)\(\s*(["'`])((?:\\.|(?!\1)[^\\])*)\1/g)) {
    const k = unq(m[1], m[2]);
    if (!en.has(k)) (miss.get(k) || miss.set(k, []).get(k)).push(path.relative(root, f));
  }
}
for (const [k, v] of miss) console.log(`${v[0]}: ${k}`);
console.log(`thiếu ${miss.size} chuỗi; en có ${en.size} khoá`);
let left = 0;
if (args.includes("--vi")) {
  const VI = /[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ]/;
  for (const f of src) {
    const lines = fs.readFileSync(f, "utf8").replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " ")).split("\n");
    lines.forEach((line, i) => {
      const code = line.replace(/(^|[^:"'`])\/\/.*$/, "$1");
      if (!VI.test(code)) return;
      // bỏ phần nằm trong t("...")
      const stripped = code.replace(/\b(?:t|tr|tn)\(\s*(["'`])((?:\\.|(?!\1)[^\\])*)\1/g, "t()");
      const hits = [];
      for (const m of stripped.matchAll(/(["'`])((?:\\.|(?!\1)[^\\])*)\1/g)) if (VI.test(m[2])) hits.push(m[2]);
      for (const m of stripped.matchAll(/>([^<>{}]*)</g)) if (VI.test(m[1])) hits.push(m[1].trim());
      if (/^\s{2,}[^<>{}"'`=;(){}]*$/.test(stripped) && VI.test(stripped)) hits.push(stripped.trim()); // dòng văn bản JSX thuần
      for (const h of hits) { left++; console.log(`VI ${path.relative(root, f)}:${i + 1}: ${h.slice(0, 90)}`); }
    });
  }
  console.log(`còn ${left} chuỗi tiếng Việt chưa bọc t()`);
}
if (args.includes("--fail") && (miss.size || left)) process.exit(1);
