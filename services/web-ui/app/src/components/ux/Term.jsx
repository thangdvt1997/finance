// Thuật ngữ có giải thích: <Term id="margin-level">Margin level</Term> hoặc <InfoTip id="var" />.
// Rê chuột/focus bàn phím hiện tooltip; chạm hoặc Enter để ghim; Esc đóng; "Xem thêm" mở trang Trợ giúp. Popover render qua portal để không bị cắt bởi overflow.
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { HelpCircle } from "lucide-react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

const cn = (...a) => twMerge(clsx(a));

function Pop({ g, anchor, id, pinned, onClose }) {
  const ref = useRef(null);
  const [pos, setPos] = useState(null);
  useEffect(() => {
    const r = anchor.getBoundingClientRect();
    const w = Math.min(320, innerWidth - 16);
    const left = Math.max(8, Math.min(r.left + r.width / 2 - w / 2, innerWidth - w - 8));
    const h = ref.current?.offsetHeight || 120;
    const below = r.bottom + 8 + h < innerHeight || r.top < h + 16;
    setPos({ left, top: below ? r.bottom + 6 : Math.max(8, r.top - h - 6), w });
  }, [anchor, g]);
  return createPortal(
    <div ref={ref} id={id} role="tooltip" className="ux-tip" style={pos ? { left: pos.left, top: pos.top, width: pos.w } : { visibility: "hidden", left: 0, top: 0 }} onMouseLeave={() => !pinned && onClose?.()}>
      <b className="block text-[12.5px]">{g.term}</b>
      <span className="block text-[12.5px] text-muted mt-[2px]">{g.short}</span>
      {g.formula && <code className="block mt-1 text-[11.5px] num text-fg">{g.formula}</code>}
      <a className="ux-link inline-block mt-1" href={`#/tro-giup?term=${g.id}`}>Xem thêm</a>
    </div>,
    document.body,
  );
}

export function Term({ id, children, className, icon, label }) {
  const uid = useId();
  const ref = useRef(null);
  const [g, setG] = useState(null); // nội dung giải thích tải lười (ux/glossary.js) khi người dùng tương tác lần đầu
  const [show, setShow] = useState(false);
  const [pin, setPin] = useState(false);
  const timer = useRef(null);
  useEffect(() => {
    if (!show) return;
    const key = (e) => { if (e.key === "Escape") { setShow(false); setPin(false); } };
    const away = (e) => { if (!ref.current?.contains(e.target) && !document.getElementById(`${uid}-p`)?.contains(e.target)) { setShow(false); setPin(false); } };
    addEventListener("keydown", key); document.addEventListener("pointerdown", away);
    return () => { removeEventListener("keydown", key); document.removeEventListener("pointerdown", away); };
  }, [show, uid]);
  const open = () => { clearTimeout(timer.current); setShow(true); if (!g) import("../../ux/glossary").then((m) => setG(m.termById(id))); };
  const close = () => { clearTimeout(timer.current); timer.current = setTimeout(() => !pin && setShow(false), 120); };
  return (
    <>
      <button ref={ref} type="button" className={cn(icon ? "ux-infotip" : "ux-term", className)} aria-describedby={show && g ? `${uid}-p` : undefined} aria-label={icon ? `Giải thích: ${label || g?.term || id}` : undefined}
        onMouseEnter={open} onMouseLeave={close} onFocus={open} onBlur={() => !pin && close()} onClick={() => { setPin((p) => !p); open(); }}>
        {icon ? <HelpCircle size={13} aria-hidden="true" /> : children}
      </button>
      {show && g && ref.current && <Pop g={g} anchor={ref.current} id={`${uid}-p`} pinned={pin} onClose={close} />}
    </>
  );
}
export const InfoTip = ({ id, className, label }) => <Term id={id} icon className={className} label={label} />;
