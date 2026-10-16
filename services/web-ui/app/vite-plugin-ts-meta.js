// Plugin Vite: đọc `export const meta = {...}` từ src/pages/*.jsx và src/widgets/*.jsx tại thời điểm build,
// để thanh điều hướng / danh mục widget có metadata ĐỒNG BỘ mà KHÔNG phải nạp (hay gộp vào bundle chính) toàn bộ trang/widget.
// Ràng buộc của meta (xem docs/WIDGETS.md): literal thuần (chuỗi, số, bool, mảng, đối tượng); icon = tên import từ "lucide-react"; không template `${}`, không hàm.
import fs from "node:fs";
import path from "node:path";

const VIRTUAL = { "virtual:ts-meta/pages": "pages", "virtual:ts-meta/widgets": "widgets" };

function extractMeta(src) {
  const m = /export\s+const\s+meta\s*=\s*/.exec(src);
  if (!m) return null;
  const start = m.index + m[0].length;
  if (src[start] !== "{") return null;
  let depth = 0, str = null, j = start;
  for (; j < src.length; j++) {
    const c = src[j];
    if (str) { if (c === "\\") j++; else if (c === str) str = null; continue; }
    if (c === '"' || c === "'" || c === "`") { str = c; continue; }
    if (c === "/" && src[j + 1] === "/") { const n = src.indexOf("\n", j); if (n < 0) break; j = n; continue; }
    if (c === "/" && src[j + 1] === "*") { const n = src.indexOf("*/", j); if (n < 0) break; j = n + 1; continue; }
    if (c === "{") depth++;
    else if (c === "}" && --depth === 0) { j++; break; }
  }
  return depth === 0 ? src.slice(start, j) : null;
}

function lucideNames(src) {
  const map = new Map(); // local -> imported
  for (const m of src.matchAll(/import\s*\{([^}]*)\}\s*from\s*["']lucide-react["']/g)) {
    for (const part of m[1].split(",")) {
      const t = part.trim();
      if (!t) continue;
      const [imp, loc] = t.split(/\s+as\s+/);
      map.set((loc || imp).trim(), imp.trim());
    }
  }
  return map;
}

export default function tsMeta() {
  let root = process.cwd();
  return {
    name: "ts-meta",
    configResolved(c) { root = c.root; },
    resolveId(id) { return VIRTUAL[id] ? "\0" + id : null; },
    load(id) {
      const key = id.startsWith("\0") ? id.slice(1) : null;
      if (!key || !VIRTUAL[key]) return null;
      const dir = path.join(root, "src", VIRTUAL[key]);
      this.addWatchFile(dir);
      let files = [];
      try { files = fs.readdirSync(dir).filter((f) => f.endsWith(".jsx")).sort(); } catch { /* chưa có thư mục */ }
      const imports = new Map(); // local -> imported
      const entries = [];
      for (const f of files) {
        const file = path.join(dir, f);
        this.addWatchFile(file);
        const src = fs.readFileSync(file, "utf8");
        const text = extractMeta(src);
        if (!text) continue;
        const used = [...lucideNames(src)].filter(([loc]) => new RegExp("\\b" + loc + "\\b").test(text));
        // meta phải là literal tự chứa (chỉ tham chiếu icon lucide). Sai thì bỏ riêng tệp đó, không làm hỏng cả ứng dụng.
        try { new Function(...used.map(([l]) => l), `"use strict"; return (${text});`)(...used.map(() => null)); }
        catch (e) { this.warn(`ts-meta: bỏ qua ${VIRTUAL[key]}/${f}: meta không hợp lệ (${e.message}). meta phải là literal thuần, icon import từ lucide-react.`); continue; }
        for (const [loc, imp] of used) imports.set(loc, imp);
        entries.push(`${JSON.stringify(f.replace(/\.jsx$/, ""))}: ${text}`);
      }
      const imp = imports.size ? `import { ${[...imports].map(([l, i]) => (l === i ? l : `${i} as ${l}`)).join(", ")} } from "lucide-react";\n` : "";
      return `${imp}export default {\n${entries.join(",\n")}\n};\n`;
    },
  };
}
