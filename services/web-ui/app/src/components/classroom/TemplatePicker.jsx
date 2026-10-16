// Thư viện mẫu kịch bản: chọn -> xem brief 3 câu -> onPick(template) (cha gửi vào chat). Không phải khuyến nghị giao dịch.
import { useState } from "react";
import { X } from "lucide-react";
import { TEMPLATES } from "./templates";
import "./guide.css";

export default function TemplatePicker({ lang = "vi", onClose, onPick, onSend }) {
  const en = lang === "en", L = (v, e) => (en ? e : v), k = en ? "en" : "vi";
  const [sel, setSel] = useState(null);
  const t = TEMPLATES.find((x) => x.id === sel);
  const use = () => { if (!t) return; onPick?.(t); if (!onPick) onSend?.(t.brief[k].join("\n")); };
  return (
    <section className="gd" aria-label={L("Mẫu kịch bản", "Scenario templates")} onKeyDown={(e) => { if (e.key === "Escape" && onClose) { e.stopPropagation(); onClose(); } }}>
      <div className="gd-head"><h2>{L("Chọn mẫu kịch bản", "Pick a scenario template")}</h2>{onClose && <button type="button" className="gd-btn" onClick={onClose} aria-label={L("Đóng mẫu", "Close templates")}><X size={16} aria-hidden="true" />{L("Đóng", "Close")}</button>}</div>
      <div className="gd-body" tabIndex={0}>
        <p className="m-0 mb-2 text-[12.5px] text-muted">{L("Chọn một mẫu rồi sửa số liệu theo ý bạn. Mẫu chỉ là điểm khởi đầu để dạy, không phải khuyến nghị giao dịch.", "Pick a template and change the numbers to your view. Templates are teaching starting points, not trading advice.")}</p>
        <div className="tp-grid" role="radiogroup" aria-label={L("Mẫu", "Templates")}>
          {TEMPLATES.map((x) => <button key={x.id} type="button" role="radio" aria-checked={sel === x.id} className={`gd-tpl${sel === x.id ? " sel" : ""}`} onClick={() => setSel(x.id)}><b>{x[k]}</b><span>{x.sd[k]}</span></button>)}
        </div>
        {t && <div className="tp-prev" aria-live="polite">
          <b>{t[k]}</b>
          <ol>{t.brief[k].map((s, i) => <li key={i}>{s}</li>)}</ol>
          {t.import && <p className="gd-note m-0 mb-2">{L("Sau khi gửi, đính ảnh hoặc tệp YAML vào ô nhập.", "After sending, attach the image or YAML file in the composer.")}</p>}
          <button type="button" className="gd-btn pri" onClick={use}>{L("Dùng mẫu này", "Use this template")}</button>
        </div>}
      </div>
    </section>
  );
}
