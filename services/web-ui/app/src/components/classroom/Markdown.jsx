import SafeImg from "./SafeImg";
// Markdown an toàn tối giản cho khung chat AI Training Class: tiêu đề, đậm/nghiêng, mã, danh sách, bảng, trích dẫn, ảnh nhúng (chỉ ảnh nội bộ /api/... hoặc data:image).
// Không dùng dangerouslySetInnerHTML; liên kết ngoài KHÔNG được render thành liên kết (chỉ văn bản).
import { Fragment } from "react";

const okImg = (u) => /^(\/api\/|data:image\/(png|jpe?g|webp);base64,)/.test(u);
function inline(s, k0 = "") {
  const out = []; let i = 0, n = 0;
  const re = /(!\[([^\]]*)\]\(([^)\s]+)\))|(`([^`]+)`)|(\*\*([^*]+)\*\*)|(\*([^*\n]+)\*)|(\[([^\]]+)\]\(([^)\s]+)\))/g;
  let m;
  while ((m = re.exec(s))) {
    if (m.index > i) out.push(s.slice(i, m.index));
    const key = `${k0}${n++}`;
    if (m[1]) out.push(okImg(m[3]) ? <SafeImg key={key} src={m[3]} alt={m[2]} loading="lazy" className="cr-img" /> : <em key={key} className="text-muted">[{m[2] || "ảnh"}]</em>);
    else if (m[4]) out.push(<code key={key} className="cr-code">{m[5]}</code>);
    else if (m[6]) out.push(<strong key={key}>{m[7]}</strong>);
    else if (m[8]) out.push(<em key={key}>{m[9]}</em>);
    else out.push(<span key={key}>{m[11]}</span>);
    i = m.index + m[0].length;
  }
  if (i < s.length) out.push(s.slice(i));
  return out;
}
const isRow = (l) => /^\s*\|.*\|\s*$/.test(l);
const cells = (l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

export default function Markdown({ text }) {
  const lines = String(text || "").replace(/\r/g, "").split("\n");
  const blocks = []; let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (/^```/.test(l)) { const buf = []; i++; while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]); i++; blocks.push(<pre key={blocks.length} className="cr-pre"><code>{buf.join("\n")}</code></pre>); continue; }
    if (isRow(l) && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(lines[i + 1])) {
      const head = cells(l); i += 2; const rows = [];
      while (i < lines.length && isRow(lines[i])) rows.push(cells(lines[i++]));
      blocks.push(<div key={blocks.length} className="cr-tw"><table className="cr-table"><thead><tr>{head.map((h, j) => <th key={j}>{inline(h)}</th>)}</tr></thead><tbody>{rows.map((r, a) => <tr key={a}>{r.map((c, j) => <td key={j}>{inline(c, `${a}-${j}-`)}</td>)}</tr>)}</tbody></table></div>);
      continue;
    }
    const h = /^(#{1,4})\s+(.*)/.exec(l);
    if (h) { blocks.push(<div key={blocks.length} className="cr-h">{inline(h[2])}</div>); i++; continue; }
    if (/^\s*[-*]\s+/.test(l) || /^\s*\d+[.)]\s+/.test(l)) {
      const ord = /^\s*\d/.test(l); const items = [];
      while (i < lines.length && (ord ? /^\s*\d+[.)]\s+/.test(lines[i]) : /^\s*[-*]\s+/.test(lines[i]))) items.push(lines[i++].replace(/^\s*(?:[-*]|\d+[.)])\s+/, ""));
      const L = ord ? "ol" : "ul";
      blocks.push(<L key={blocks.length} className="cr-list">{items.map((t, j) => <li key={j}>{inline(t, `${j}-`)}</li>)}</L>); continue;
    }
    if (/^>\s?/.test(l)) { const buf = []; while (i < lines.length && /^>\s?/.test(lines[i])) buf.push(lines[i++].replace(/^>\s?/, "")); blocks.push(<blockquote key={blocks.length} className="cr-quote">{inline(buf.join(" "))}</blockquote>); continue; }
    if (!l.trim()) { i++; continue; }
    const buf = [l]; i++;
    while (i < lines.length && lines[i].trim() && !/^(```|#{1,4}\s|>|\s*[-*]\s|\s*\d+[.)]\s)/.test(lines[i]) && !isRow(lines[i])) buf.push(lines[i++]);
    blocks.push(<p key={blocks.length} className="cr-p">{buf.map((t, j) => <Fragment key={j}>{j > 0 && <br />}{inline(t, `${j}-`)}</Fragment>)}</p>);
  }
  return <div className="cr-md">{blocks}</div>;
}
