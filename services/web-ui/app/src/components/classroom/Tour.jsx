// Tour 5 bước: highlight vùng bằng [data-tour="..."]. Bỏ qua / mở lại được. Danh sách neo: docs/handoff/UX_TOUR_ANCHORS.md.
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import "./guide.css";

const KEY = "cr-tour-done";
export const isTourSeen = () => { try { return localStorage.getItem(KEY) === "1"; } catch { return false; } };
export const markTourSeen = (v = true) => { try { if (v) localStorage.setItem(KEY, "1"); else localStorage.removeItem(KEY); } catch { /* bỏ qua */ } };
export const STEPS = [
  { a: "rooms", vi: ["Phòng học", "Mỗi kịch bản một phòng. Tạo phòng mới rồi đặt tên kịch bản."], en: ["Classrooms", "One room per scenario. Create a room and name the scenario."] },
  { a: "chat", vi: ["Trò chuyện với AI", "Mô tả kịch bản bằng 3 câu, có số cụ thể. AI sẽ hỏi lại từng chỗ còn mơ hồ."], en: ["Chat with the AI", "Describe the scenario in 3 sentences with concrete numbers. The AI asks about each vague spot."] },
  { a: "profile", vi: ["Hồ sơ kịch bản", "Điền dần theo hội thoại. Bạn sửa trực tiếp, xác nhận từng hàng."], en: ["Scenario profile", "Fills in as you chat. Edit directly and confirm each row."] },
  { a: "clarity", vi: ["Độ rõ ý tưởng", "Điểm 0-100. Hãy nâng hàng thấp nhất trước: càng rõ ý tưởng, kết quả càng đáng tin."], en: ["Idea clarity", "A 0-100 score. Raise the lowest row first: the clearer the idea, the more trustworthy the result."] },
  { a: "actions", vi: ["Nút hành động", "Lưu phiên bản, Chạy test, Xuất; mở Xem demo hay Cách dạy bất cứ lúc nào. Muốn gì cứ nói bằng lời bình thường. Chỉ nghiên cứu/giấy, không đặt lệnh."], en: ["Action buttons", "Save version, Run test, Export; open the demo or teaching guide any time. Just say what you want in plain words. Research/paper only, no orders."] },
];
const W = 340;

export default function Tour({ lang = "vi", onClose }) {
  const en = lang === "en", L = (v, e) => (en ? e : v);
  const [i, setI] = useState(0), [box, setBox] = useState(null), [vp, setVp] = useState({ w: window.innerWidth, h: window.innerHeight });
  const pop = useRef(null);
  const s = STEPS[i], [title, body] = en ? s.en : s.vi;
  const close = useCallback((seen = true) => { markTourSeen(seen); onClose?.(); }, [onClose]);

  const measure = useCallback(() => {
    setVp({ w: window.innerWidth, h: window.innerHeight });
    const el = document.querySelector(`[data-tour="${STEPS[i].a}"]`);
    if (!el || !el.getClientRects().length) { setBox(null); return; }
    const r = el.getBoundingClientRect(); setBox({ x: r.left - 4, y: r.top - 4, w: r.width + 8, h: r.height + 8 });
  }, [i]);
  useLayoutEffect(() => {
    const el = document.querySelector(`[data-tour="${STEPS[i].a}"]`);
    try { el?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "auto" }); } catch { /* bỏ qua */ }
    measure();
  }, [i, measure]);
  useEffect(() => { window.addEventListener("resize", measure); window.addEventListener("scroll", measure, true); return () => { window.removeEventListener("resize", measure); window.removeEventListener("scroll", measure, true); }; }, [measure]);
  useEffect(() => { pop.current?.querySelector("[data-autofocus]")?.focus({ preventScroll: true }); }, [i]);

  const key = (e) => {
    if (e.key === "Escape") { e.stopPropagation(); close(true); }
    else if (e.key === "ArrowRight") setI((x) => Math.min(STEPS.length - 1, x + 1));
    else if (e.key === "ArrowLeft") setI((x) => Math.max(0, x - 1));
    else if (e.key === "Tab") { const f = [...pop.current.querySelectorAll("button")].filter((b) => !b.disabled); if (!f.length) return; const a = document.activeElement; if (e.shiftKey && a === f[0]) { e.preventDefault(); f[f.length - 1].focus(); } else if (!e.shiftKey && a === f[f.length - 1]) { e.preventDefault(); f[0].focus(); } }
  };
  const pw = Math.min(W, vp.w - 24);
  let left = Math.max(12, (vp.w - pw) / 2), top = Math.max(12, vp.h / 2 - 80);
  if (box) { const below = box.y + box.h + 12 + 190 < vp.h; top = below ? box.y + box.h + 12 : Math.max(12, box.y - 12 - 190); left = Math.min(Math.max(12, box.x), vp.w - pw - 12); if (!below && box.y < 202) top = Math.min(vp.h - 202, box.y + 12); }
  const last = i === STEPS.length - 1;
  return (
    <div className="tr-veil" onKeyDown={key}>
      {box ? <div className="tr-hole" style={{ left: box.x, top: box.y, width: box.w, height: box.h }} aria-hidden="true" /> : <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.62)" }} aria-hidden="true" />}
      <div className="tr-pop" ref={pop} role="dialog" aria-modal="true" aria-labelledby="tr-t" aria-describedby="tr-b" style={{ left, top, width: pw }}>
        <p className="m-0 text-[11.5px] text-muted">{L("Hướng dẫn nhanh", "Quick tour")} · {i + 1}/{STEPS.length}</p>
        <h3 id="tr-t">{title}</h3><p id="tr-b">{body}</p>
        <div className="tr-foot">
          <button type="button" className="gd-btn" onClick={() => close(true)}>{L("Bỏ qua", "Skip")}</button>
          <span style={{ flex: 1 }} />
          <button type="button" className="gd-btn" onClick={() => setI(i - 1)} disabled={i === 0}>{L("Lùi", "Back")}</button>
          <button type="button" className="gd-btn pri" data-autofocus onClick={() => (last ? close(true) : setI(i + 1))}>{last ? L("Xong", "Done") : L("Tiếp", "Next")}</button>
        </div>
      </div>
    </div>
  );
}
