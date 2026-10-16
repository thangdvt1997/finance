// Thành phần bộ nhớ ngay trong chat: thẻ xác nhận "Mình ghi nhớ: … đúng không?" [Đúng][Sửa][Đừng nhớ], thẻ mâu thuẫn, chỉ báo "Mình nhớ lần trước bạn nói …".
import { useState } from "react";
import { Check, Pencil, X } from "lucide-react";
import { cn } from "../ui";
import { errText, mw } from "./memoryApi";
import "./memory.css";

/** cards: [{id, kind:'confirm'|'clarify', text, conflict_id?, labels?}] từ SSE 'memory' hoặc rooms/{rid}/memory/extract. */
export function MemoryCards({ cards = [], lang = "vi", onChanged, onOpenConflict }) {
  const en = lang === "en";
  const t = (vi, e) => (en ? e : vi);
  const [st, setSt] = useState({}), [edit, setEdit] = useState(null), [text, setText] = useState(""), [err, setErr] = useState(null), [busy, setBusy] = useState(false);
  if (!cards.length) return null;
  const run = async (c, action) => {
    setBusy(true); setErr(null);
    try {
      if (action === "confirm") await mw("POST", `/memory/${encodeURIComponent(c.id)}/confirm`, {});
      else if (action === "reject") await mw("POST", `/memory/${encodeURIComponent(c.id)}/reject`, {});
      else await mw("PATCH", `/memory/${encodeURIComponent(c.id)}`, { text: text.trim() });
      setSt((s) => ({ ...s, [c.id]: action })); setEdit(null); onChanged?.(action, c);
    } catch (e) { setErr(errText(e, en)); } finally { setBusy(false); }
  };
  const done = { confirm: t("Đã ghi nhớ.", "Remembered."), reject: t("Đã bỏ, AI sẽ không nhớ điều này.", "Dropped, the AI will not remember this."), edit: t("Đã sửa và ghi nhớ bản mới.", "Edited and remembered the new version.") };
  return (
    <div role="group" aria-label={t("Xác nhận bộ nhớ", "Memory confirmation")}>
      {cards.map((c) => {
        const d = st[c.id];
        return (
          <div key={c.id} className={cn("mem-card", d && "done")}>
            <p className="mem-card-t">{c.text || t("Mình ghi nhớ điều này, đúng không?", "I will remember this, right?")}</p>
            {d ? <p className="mem-msg" role="status">{done[d]}</p> : edit === c.id ? (
              <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) run(c, "edit"); }} className="grid gap-1">
                <label className="mem-msg" htmlFor={`mc-${c.id}`}>{t("Sửa lại cho đúng ý bạn", "Correct it")}</label>
                <textarea id={`mc-${c.id}`} className="cr-inp" value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} style={{ minHeight: 72 }} />
                <div className="mem-act"><button type="submit" className="mem-btn pri" disabled={busy || !text.trim()}>{t("Lưu", "Save")}</button><button type="button" className="mem-btn" onClick={() => setEdit(null)}>{t("Huỷ", "Cancel")}</button></div>
              </form>
            ) : c.kind === "clarify" ? (
              <div className="mem-act"><button type="button" className="mem-btn pri" onClick={() => onOpenConflict?.(c)}>{t("Xem và chọn bản đúng", "Review and pick the right one")}</button></div>
            ) : (
              <div className="mem-act">
                <button type="button" className="mem-btn pri" disabled={busy} onClick={() => run(c, "confirm")}><Check size={14} aria-hidden="true" />{en ? "Right" : (c.labels?.confirm || "Đúng")}</button>
                <button type="button" className="mem-btn" disabled={busy} onClick={() => { setEdit(c.id); setText(String(c.text || "").replace(/^Mình ghi nhớ:\s*/i, "").replace(/\s*Đúng không\?\s*$/i, "")); }}><Pencil size={14} aria-hidden="true" />{en ? "Edit" : (c.labels?.edit || "Sửa")}</button>
                <button type="button" className="mem-btn dng" disabled={busy} onClick={() => run(c, "reject")}><X size={14} aria-hidden="true" />{en ? "Do not remember" : (c.labels?.reject || "Đừng nhớ")}</button>
              </div>
            )}
          </div>
        );
      })}
      {err && <p role="alert" className="mem-err">{err}</p>}
    </div>
  );
}

/** Chỉ báo dưới tin AI khi dùng bộ nhớ: "Mình nhớ lần trước bạn nói …" + nút xem/ sửa nguồn. items: [{id,text,status}] */
export function MemoryUsed({ items = [], lang = "vi", onOpen }) {
  const en = lang === "en";
  const [open, setOpen] = useState(false);
  if (!Array.isArray(items) || !items.length) return null;
  const first = String(items[0].text || "").slice(0, 90);
  return (
    <div className="mem-used">
      <button type="button" className="mem-used-b" aria-expanded={open} onClick={() => setOpen(!open)}>
        {en ? `I remember you said: "${first}"` : `Mình nhớ lần trước bạn nói: "${first}"`}{items.length > 1 ? (en ? ` (+${items.length - 1})` : ` (+${items.length - 1})`) : ""}
      </button>
      {open && (
        <ul className="mem-list" aria-label={en ? "Memory used" : "Bộ nhớ đã dùng"}>
          {items.map((m) => (
            <li key={m.id} className="mem-item"><p className="mem-text">{m.text}</p>
              <div className="mem-act"><button type="button" className="mem-btn" onClick={() => onOpen?.(m.id)}>{en ? "View / edit source" : "Xem / sửa nguồn"}</button></div></li>
          ))}
        </ul>
      )}
    </div>
  );
}
