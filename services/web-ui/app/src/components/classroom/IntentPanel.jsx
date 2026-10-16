// Dòng "AI hiểu ý bạn là", thẻ xác nhận hành động (câu hỏi tự nhiên) và option gợi ý bấm được. Không có lệnh "/" hiển thị cho người dùng.
import { useState } from "react";
import { Lightbulb } from "lucide-react";
import { marketCommand, splitHighlights } from "./intentApi";
import { useCls } from "./ctx";
import "./intent.css";

const L = (o, k, lang) => (lang === "en" ? o[`${k}_en`] || o[`${k}_vi`] : o[`${k}_vi`]) || "";

function Card({ card, busy, onRun, onNo, onPlain }) {
  const { t, lang } = useCls();
  const [form, setForm] = useState(null);
  const change = card.buttons.find((b) => b.id === "change");
  const cmd = form ? marketCommand(form.symbol, form.tf) : null;
  return (
    <section className="it-card" role="group" aria-label={t("Xác nhận hành động", "Confirm action")} data-testid="intent-card">
      <p>{L(card, "question", lang)}</p>
      {!form && (
        <div className="it-row">
          {card.buttons.map((b) => b.id === "run" ? <button key={b.id} type="button" className="it-btn pri" disabled={busy} onClick={() => onRun(b.command_text, card)}>{L(b, "label", lang)}</button>
            : b.id === "change" ? <button key={b.id} type="button" className="it-btn" disabled={busy} onClick={() => setForm({ symbol: b.form?.symbol || "", tf: (b.form?.tf || "H1").toLowerCase() })}>{L(b, "label", lang)}</button>
            : <button key={b.id} type="button" className="it-btn" disabled={busy} onClick={onNo}>{L(b, "label", lang)}</button>)}
          <button type="button" className="it-btn lnk" onClick={onPlain}>{t("Gửi như tin nhắn thường", "Send as a normal message")}</button>
        </div>
      )}
      {form && change && (
        <div className="it-row">
          <label className="text-[12px]">{t("Mã", "Symbol")} <input className="it-in" style={{ width: 110 }} value={form.symbol} maxLength={12} placeholder="XAUUSD" onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })} /></label>
          <label className="text-[12px]">{t("Khung", "Timeframe")} <select className="it-in" value={form.tf} onChange={(e) => setForm({ ...form, tf: e.target.value })}>{(change.form.tfs || ["M15", "H1", "H4", "D1"]).map((x) => <option key={x} value={x.toLowerCase()}>{x}</option>)}</select></label>
          <button type="button" className="it-btn pri" disabled={busy || !cmd} onClick={() => onRun(cmd, card)}>{t("Thử trên mã/khung này", "Try on this market")}</button>
          <button type="button" className="it-btn" onClick={() => setForm(null)}>{t("Quay lại", "Back")}</button>
        </div>
      )}
      <small className="text-muted">{t("Chỉ nghiên cứu và mô phỏng; không đặt lệnh thật.", "Research and simulation only; no real orders.")}</small>
    </section>
  );
}

export default function IntentPanel({ und, opts, card, busy, onOption, onRun, onNo, onPlain, onNotThis, onAlt }) {
  const { t, lang } = useCls();
  const [why, setWhy] = useState(false), [alts, setAlts] = useState(false);
  const it = und?.intent;
  const txt = (und?.text || "").slice(0, 220);
  return (
    <div className="it" aria-live="polite">
      {it && (
        <div className="it-und" role="status" data-testid="intent-understood">
          <span className="it-lbl">{t("AI hiểu ý bạn là:", "The AI understood:")} {L(it, "label", lang)}</span>
          {it.level === "weak" && <span className="it-conf">{t("(chưa chắc)", "(not sure)")}</span>}
          {txt && <q>“{splitHighlights(txt, und.highlights).map((s, i) => s.hl ? <mark key={i}>{s.t}</mark> : <span key={i}>{s.t}</span>)}”</q>}
          <button type="button" className="it-btn lnk" aria-expanded={alts} onClick={() => { setAlts((v) => !v); if (!alts) onNotThis?.(); }}>{t("Không phải ý này", "Not what I meant")}</button>
          {it.level === "weak" && (it.command_text || it.ui) && <button type="button" className="it-btn" disabled={busy} onClick={() => onAlt(it)}>{t("Đúng, làm luôn", "Yes, do it")}</button>}
        </div>
      )}
      {it && alts && (
        <div className="it-row" role="group" aria-label={t("Chọn lại ý định", "Pick another intent")}>
          {(und.alternatives || []).map((a) => <button key={a.key} type="button" className="it-btn" disabled={busy} onClick={() => onAlt(a)}>{L(a, "label", lang)}</button>)}
          <button type="button" className="it-btn" onClick={onPlain}>{t("Chỉ là tin nhắn thường", "Just a normal message")}</button>
        </div>
      )}
      {card && <Card card={card} busy={busy} onRun={onRun} onNo={onNo} onPlain={onPlain} />}
      {opts?.length > 0 && !card && (
        <div>
          <ul className="it-opts" aria-label={t("Gợi ý cho bước tiếp theo", "Suggestions for the next step")} data-testid="intent-options">
            {opts.slice(0, 4).map((o) => (
              <li key={o.id}>
                <button type="button" className="it-opt" disabled={busy} title={why ? undefined : (o.why || []).join("; ")} onClick={() => onOption(o)}>
                  {L(o, "label", lang)}{o.heavy ? <span className="it-heavy">{t("cần xác nhận", "needs confirmation")}</span> : null}
                  {why && (o.why || []).length > 0 && <small>{t("Vì sao: ", "Why: ")}{(lang === "en" ? o.why_en : o.why).filter(Boolean).slice(0, 2).join("; ")}</small>}
                </button>
              </li>
            ))}
          </ul>
          <button type="button" className="it-btn lnk" onClick={() => setWhy((v) => !v)} aria-pressed={why}><Lightbulb size={12} aria-hidden="true" /> {why ? t("Ẩn lý do gợi ý", "Hide why") : t("Vì sao gợi ý này?", "Why these suggestions?")}</button>
        </div>
      )}
    </div>
  );
}
