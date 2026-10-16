// Checklist "Buổi học đầu tiên". Tick tự động từ props.progress (số hoặc boolean), xem docs/handoff/UX_TOUR_ANCHORS.md.
import { Check, X } from "lucide-react";
import "./guide.css";

const n = (v) => (typeof v === "boolean" ? +v : Number.isFinite(+v) ? +v : 0);
export const CHECK_STEPS = [
  { id: "room", vi: "Tạo kịch bản (phòng mới)", en: "Create a scenario (new room)", hv: "Bấm Phòng mới và đặt tên.", he: "Press New room and name it.", ok: (p) => n(p.rooms ?? p.created) >= 1 },
  { id: "answers", vi: "Trả lời 5 câu của AI", en: "Answer 5 AI questions", hv: "Trả lời bằng số cụ thể.", he: "Answer with concrete numbers.", ok: (p) => n(p.answers ?? p.answered) >= 5, of: (p) => [n(p.answers ?? p.answered), 5] },
  { id: "labels", vi: "Gắn nhãn 6 ví dụ", en: "Label 6 examples", hv: "Nhờ AI tìm ví dụ rồi bấm Đ / S / G.", he: "Ask the AI to find examples, then press R / W / C.", ok: (p) => n(p.labels ?? p.labelled) >= 6, of: (p) => [n(p.labels ?? p.labelled), 6] },
  { id: "save", vi: "Lưu phiên bản", en: "Save a version", hv: "Bấm Lưu phiên bản hoặc nói “lưu lại”.", he: "Press Save version or say “save it”.", ok: (p) => n(p.versions ?? p.saved) >= 1 },
  { id: "test", vi: "Chạy test", en: "Run a test", hv: "Bấm Chạy test; kết quả trung thực, có thể là 'chưa chứng minh'.", he: "Press Run test; the result is honest and may be 'unproven'.", ok: (p) => n(p.tests ?? p.tested) >= 1 },
];

export default function Checklist({ lang = "vi", progress = {}, onClose, onSend }) {
  const en = lang === "en", L = (v, e) => (en ? e : v), p = progress || {};
  const done = CHECK_STEPS.filter((s) => s.ok(p)).length;
  return (
    <section className="gd" aria-label={L("Buổi học đầu tiên", "Your first lesson")} onKeyDown={(e) => { if (e.key === "Escape" && onClose) { e.stopPropagation(); onClose(); } }}>
      <div className="gd-head"><h2>{L("Buổi học đầu tiên", "Your first lesson")} <span className="text-[12px] text-muted num">{done}/{CHECK_STEPS.length}</span></h2>{onClose && <button type="button" className="gd-btn" onClick={onClose} aria-label={L("Ẩn checklist", "Hide checklist")}><X size={16} aria-hidden="true" />{L("Ẩn", "Hide")}</button>}</div>
      <div className="gd-body" tabIndex={0}>
        <div className="dm-bar mb-2" role="progressbar" aria-valuemin={0} aria-valuemax={CHECK_STEPS.length} aria-valuenow={done} aria-label={L("Tiến độ buổi học đầu tiên", "First lesson progress")}><i style={{ width: `${(done / CHECK_STEPS.length) * 100}%` }} /></div>
        <ol className="ck" style={{ listStyle: "none" }}>
          {CHECK_STEPS.map((s) => { const ok = s.ok(p), of = s.of?.(p); return (
            <li key={s.id} className={ok ? "done" : ""}>
              <span className="box" aria-hidden="true">{ok && <Check size={14} />}</span>
              <span><span className="t">{en ? s.en : s.vi}</span>{of && !ok ? <span className="num text-muted"> ({Math.min(of[0], of[1])}/{of[1]})</span> : null}
                <span className="hint">{en ? s.he : s.hv}</span><span className="sr-only">{ok ? L("Đã xong", "Done") : L("Chưa xong", "Not done")}</span></span>
            </li>); })}
        </ol>
        {done === CHECK_STEPS.length && <p className="gd-note" role="status">{L("Hoàn thành. Hãy lặp lại với kịch bản khác; nhớ rằng kết quả test chỉ là nghiên cứu, không bảo đảm lợi nhuận.", "Complete. Repeat with another scenario; remember test results are research only and never guarantee profit.")}</p>}
        {onSend && done < CHECK_STEPS.length && <button type="button" className="gd-btn mt-2" onClick={() => onSend(L("/hoi-them", "/hoi-them"))}>{L("Nhờ AI hỏi tiếp", "Ask the AI to continue")}</button>}
      </div>
    </section>
  );
}
