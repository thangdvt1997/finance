// Xuất bảng/biểu đồ: CSV (UTF-8 BOM, mở thẳng bằng Excel), XLSX thật (zip không nén, tự viết ~60 dòng), TSV/HTML để dán, PNG (html-to-image nạp lười), in.
import { fmtCfg } from "./fmtconfig";

const enc = new TextEncoder();

// ---------- đọc bảng DOM ----------
// Văn bản nhìn thấy của một ô: duyệt các nút chữ đang hiển thị (bỏ .sr-only, aria-hidden, phần tử ẩn), nối bằng dấu cách để "EURUSD" + "Forex" + "2 giờ trước" không dính nhau.
const cellText = (c) => {
  const parts = [];
  const w = document.createTreeWalker(c, NodeFilter.SHOW_TEXT);
  for (let n; (n = w.nextNode());) {
    const t = n.nodeValue.replace(/\s+/g, " ").trim();
    const e = n.parentElement;
    if (!t || !e || e.closest(".sr-only, [aria-hidden='true'], style, script") || !e.getClientRects().length) continue;
    parts.push(t);
  }
  return parts.join(" ").replace(/\s+/g, " ").trim();
};
/** Ma trận chuỗi hiển thị của một <table> (hàng tiêu đề trước). Bỏ cột/hàng ẩn (display:none). */
export function tableToMatrix(table) {
  const rows = [];
  for (const tr of table.querySelectorAll("tr")) {
    if (tr.offsetParent === null && getComputedStyle(tr).display === "none") continue;
    const cells = [...tr.children].filter((c) => /^(TD|TH)$/.test(c.tagName) && getComputedStyle(c).display !== "none");
    if (!cells.length) continue;
    const out = [];
    for (const c of cells) {
      out.push(cellText(c));
      for (let i = 1; i < (c.colSpan || 1); i++) out.push("");
    }
    rows.push(out);
  }
  return rows;
}

/** Tên gợi ý cho bảng: aria-label/caption, tiêu đề panel gần nhất, hoặc "Bảng n". */
export function tableTitle(table, i = 0) {
  const cap = table.querySelector("caption")?.textContent?.trim() || table.getAttribute("aria-label");
  if (cap) return cap;
  const sec = table.closest("section[aria-labelledby], .panel");
  const h = sec?.querySelector("h2, h3");
  return h?.textContent?.trim() || `Bảng ${i + 1}`;
}
export function findTables(root = document.getElementById("main")) {
  return [...(root?.querySelectorAll("table") || [])].filter((t) => t.rows.length > 1 && t.getClientRects().length).map((el, i) => ({ el, title: tableTitle(el, i), rows: el.rows.length - 1 }));
}

/** Chuỗi số hiển thị -> số thô (theo kiểu số đang chọn). Không đổi nếu không giống số. */
export function rawNumber(s) {
  const t = String(s).replace(/[\s ]/g, "");
  if (!/^[+-]?\d[\d.,]*%?$/.test(t)) return null;
  const pct = t.endsWith("%");
  let b = pct ? t.slice(0, -1) : t;
  if (fmtCfg.num === "vi") b = b.replace(/\./g, "").replace(",", "."); else b = b.replace(/,/g, "");
  const n = Number(b);
  return Number.isFinite(n) ? (pct ? { n, pct: true } : { n }) : null;
}

// ---------- CSV / TSV ----------
const q = (s, sep) => (new RegExp(`["\\n\\r${sep}]`).test(s) ? `"${s.replace(/"/g, '""')}"` : s);
export function toCSV(matrix, { raw = true, sep = "," } = {}) {
  return matrix.map((r, ri) => r.map((c) => { if (raw && ri > 0) { const v = rawNumber(c); if (v) return String(v.n); } return q(String(c), sep); }).join(sep)).join("\r\n");
}
export const toTSV = (matrix) => matrix.map((r) => r.map((c) => c.replace(/[\t\r\n]+/g, " ")).join("\t")).join("\n");
export function toHTML(matrix) {
  const e = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  return `<table>${matrix.map((r, i) => `<tr>${r.map((c) => `<${i ? "td" : "th"}>${e(c)}</${i ? "td" : "th"}>`).join("")}</tr>`).join("")}</table>`;
}

// ---------- XLSX ----------
let CRC = null;
function crc32(b) {
  if (!CRC) { CRC = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; CRC[n] = c >>> 0; } }
  let c = 0xffffffff;
  for (let i = 0; i < b.length; i++) c = CRC[(c ^ b[i]) & 255] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function zip(files) { // files: [{name, data(Uint8Array)}], phương pháp STORE
  const parts = [], central = [];
  let off = 0;
  const u16 = (n) => [n & 255, (n >>> 8) & 255], u32 = (n) => [n & 255, (n >>> 8) & 255, (n >>> 16) & 255, (n >>> 24) & 255];
  for (const f of files) {
    const name = enc.encode(f.name), crc = crc32(f.data), sz = f.data.length;
    const lh = new Uint8Array([0x50, 0x4b, 3, 4, 20, 0, 0, 8, 0, 0, 0, 0, 0x21, 0, ...u32(crc), ...u32(sz), ...u32(sz), ...u16(name.length), 0, 0]);
    parts.push(lh, name, f.data);
    central.push(new Uint8Array([0x50, 0x4b, 1, 2, 20, 0, 20, 0, 0, 8, 0, 0, 0, 0, 0x21, 0, ...u32(crc), ...u32(sz), ...u32(sz), ...u16(name.length), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ...u32(off)]), name);
    off += lh.length + name.length + sz;
  }
  const cs = central.reduce((a, b) => a + b.length, 0);
  const end = new Uint8Array([0x50, 0x4b, 5, 6, 0, 0, 0, 0, ...u16(files.length), ...u16(files.length), ...u32(cs), ...u32(off), 0, 0]);
  return new Blob([...parts, ...central, end], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
}
const colName = (i) => { let s = ""; for (i++; i > 0; i = Math.floor((i - 1) / 26)) s = String.fromCharCode(65 + ((i - 1) % 26)) + s; return s; };
const xe = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, "");
export function toXLSX(matrix, sheetName = "Dữ liệu") {
  const rows = matrix.map((r, ri) => `<row r="${ri + 1}">${r.map((c, ci) => {
    const ref = `${colName(ci)}${ri + 1}`;
    const v = ri > 0 ? rawNumber(c) : null;
    if (v) return `<c r="${ref}"${v.pct ? ' s="1"' : ""}><v>${v.pct ? v.n / 100 : v.n}</v></c>`;
    return c === "" ? "" : `<c r="${ref}"${ri === 0 ? ' s="2"' : ""} t="inlineStr"><is><t xml:space="preserve">${xe(c)}</t></is></c>`;
  }).join("")}</row>`).join("");
  const cols = matrix[0]?.length || 1;
  const files = {
    "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
    "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
    "xl/workbook.xml": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="${xe(sheetName.replace(/[\\/?*[\]:]/g, " ").slice(0, 31) || "Sheet1")}" sheetId="1" r:id="rId1"/></sheets></workbook>`,
    "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
    "xl/styles.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="10" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs></styleSheet>',
    "xl/worksheets/sheet1.xml": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="${cols}" width="18" customWidth="1"/></cols><sheetData>${rows}</sheetData></worksheet>`,
  };
  return zip(Object.entries(files).map(([name, s]) => ({ name, data: enc.encode(s) })));
}

// ---------- tải xuống / PNG / in ----------
export function download(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.rel = "noopener";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}
const slug = (s) => String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/gi, "d").replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-|-$/g, "").toLowerCase().slice(0, 40) || "du-lieu";
export const stamp = () => new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "");
export const fileBase = (title) => `${slug(title)}-${stamp()}`;

export const downloadCSV = (m, title) => download(new Blob(["﻿" + toCSV(m)], { type: "text/csv;charset=utf-8" }), `${fileBase(title)}.csv`);
export const downloadXLSX = (m, title) => download(toXLSX(m, title), `${fileBase(title)}.xlsx`);

// CSS phông chữ nhúng sẵn (data URL) để html-to-image không tự dựng URL tương đối (vi phạm CSP base-uri) và ảnh dùng đúng phông Inter/JetBrains.
let fontCss = null;
async function getFontCSS() {
  if (fontCss != null) return fontCss;
  const blobToData = (b) => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(b); });
  const out = [];
  for (const sh of [...document.styleSheets]) {
    let rules; try { rules = sh.cssRules; } catch { continue; }
    for (const rule of rules) {
      if (!(rule instanceof CSSFontFaceRule)) continue;
      const src = rule.style.getPropertyValue("src");
      const m = /url\(["']?([^"')]+\.woff2)["']?\)/.exec(src);
      if (!m || !/(latin|vietnamese)/.test(m[1])) continue; // chỉ bộ chữ cần cho tiếng Việt/Latin
      try {
        const url = new URL(m[1], sh.href || location.href).href;
        const data = await blobToData(await (await fetch(url)).blob());
        out.push(`@font-face{font-family:${rule.style.getPropertyValue("font-family")};font-weight:${rule.style.getPropertyValue("font-weight")};font-style:${rule.style.getPropertyValue("font-style") || "normal"};unicode-range:${rule.style.getPropertyValue("unicode-range") || "U+0-10FFFF"};src:url(${data}) format("woff2");}`);
      } catch { /* bỏ phông lỗi */ }
    }
  }
  return (fontCss = out.join("\n"));
}

/** Chụp một phần tử thành PNG (nạp html-to-image khi cần). */
export async function downloadPNG(node, title) {
  const { toPng } = await import("html-to-image");
  const bg = getComputedStyle(document.body).backgroundColor;
  const opts = { pixelRatio: Math.min(2, window.devicePixelRatio || 1) * 1.5, backgroundColor: bg, cacheBust: false, filter: (n) => !(n.classList && n.classList.contains("no-capture")), fontEmbedCSS: await getFontCSS() };
  const url = await toPng(node, opts);
  const a = document.createElement("a");
  a.href = url; a.download = `${fileBase(title)}.png`; document.body.appendChild(a); a.click(); a.remove();
}

export async function copyMatrix(matrix) {
  const tsv = toTSV(matrix);
  try {
    if (window.ClipboardItem && navigator.clipboard?.write) {
      await navigator.clipboard.write([new ClipboardItem({ "text/plain": new Blob([tsv], { type: "text/plain" }), "text/html": new Blob([toHTML(matrix)], { type: "text/html" }) })]);
      return true;
    }
    await navigator.clipboard.writeText(tsv);
    return true;
  } catch { return false; }
}

export function printPage() {
  const el = document.documentElement;
  el.dataset.printing = "1";
  const done = () => { delete el.dataset.printing; removeEventListener("afterprint", done); };
  addEventListener("afterprint", done);
  setTimeout(() => window.print(), 60);
  setTimeout(done, 60000);
}
