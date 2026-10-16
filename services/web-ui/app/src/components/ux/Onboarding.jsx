// Tour làm quen lần đầu (tiếng Việt): làm nổi bật từng phần giao diện bằng [data-tour]. Phím: Enter/→ tiếp, ← lùi, Esc bỏ qua.
// Phần tử không hiện (ví dụ thanh bên trên điện thoại) -> thẻ hiện giữa màn hình, không làm sáng.
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { updateSettings, useSettings } from "../../ux/settings";
import { usePrefsState } from "../../lib/prefs";

export const TOUR_VERSION = 1;
const STEPS = [
  { t: "Chào mừng đến Trạm thị trường", b: "Giao diện theo dõi giá, tin, lịch kinh tế và tài khoản MT4/MT5 ở chế độ chỉ-đọc. Hơn một phút để làm quen; bạn có thể bỏ qua bất kỳ lúc nào và xem lại ở Trợ giúp." },
  { sel: "nav", t: "Điều hướng theo nhóm", b: "Bốn nhóm: Thị trường, Thông tin, Tài khoản, Vận hành. Trên điện thoại, bốn mục chính nằm dưới màn hình, nút “Thêm” mở toàn bộ trang. Phím tắt: nhấn g rồi một chữ (ví dụ g m = Thị trường)." },
  { sel: "search", t: "Tìm nhanh và lệnh nhanh (Ctrl K)", b: "Gõ tên trang, mã (eurusd), tin hoặc thuật ngữ. Thử: “cảnh báo eurusd 1.0850” để tạo cảnh báo, “>” để xem lệnh, “?” để tra thuật ngữ." },
  { sel: "status", t: "Trạng thái dữ liệu", b: "Chấm xanh “Trực tiếp” nghĩa là dữ liệu đang chảy về. Huy hiệu “N phút trước” cho biết độ tươi: xanh mới, vàng chậm, đỏ cũ, xám là thị trường nghỉ." },
  { sel: "bell", t: "Trung tâm thông báo", b: "Cảnh báo giá của bạn, tin quan trọng, tín hiệu chuyên gia và sự cố hệ thống gom về đây. Bật âm báo hoặc thông báo trình duyệt trong Cài đặt." },
  { sel: "tools", t: "Công cụ trang", b: "Xuất bảng ra CSV hoặc Excel, lưu ảnh PNG, in/lưu PDF, sao chép liên kết giữ nguyên mã và khung, đánh dấu trang để quay lại nhanh." },
  { sel: "settings", t: "Cài đặt riêng của bạn", b: "Giao diện sáng/tối/tự động, màu nhấn, mật độ, cỡ chữ, múi giờ, màu tăng/giảm (có chế độ cho người mù màu). Cài đặt lưu theo tài khoản và đồng bộ giữa các thiết bị." },
  { t: "Lưu ý quan trọng", b: "Dữ liệu chỉ để tham khảo, không phải khuyến nghị đầu tư. Hệ thống không đặt, sửa hay đóng lệnh. Cần giải thích thuật ngữ? Rê chuột vào từ có gạch chấm hoặc mở Trợ giúp." },
];

const visible = (el) => !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== "hidden";

export function Onboarding({ seq = 0 }) {
  const [s] = useSettings();
  const prefs = usePrefsState();
  const [open, setOpen] = useState(false);
  const [i, setI] = useState(0);
  const [rect, setRect] = useState(null);
  const nextRef = useRef(null);

  // tự mở lần đầu (sau khi tuỳ chọn máy chủ đã tải để biết đã xem trên thiết bị khác chưa)
  useEffect(() => {
    if (s.onboarded >= TOUR_VERSION) return;
    const t = setTimeout(() => { if (!document.querySelector('[aria-modal="true"]')) { setI(0); setOpen(true); } }, prefs.loaded ? 900 : 3500);
    return () => clearTimeout(t);
  }, [prefs.loaded, s.onboarded]);
  useEffect(() => { if (seq > 0) { setI(0); setOpen(true); } }, [seq]);

  const step = STEPS[i];
  const measure = useCallback(() => {
    if (!open) return;
    const el = step?.sel ? [...document.querySelectorAll(`[data-tour="${step.sel}"]`)].find(visible) : null;
    if (el) { el.scrollIntoView({ block: "nearest", inline: "nearest" }); const r = el.getBoundingClientRect(); setRect({ x: r.left, y: r.top, w: r.width, h: r.height }); } else setRect(null);
  }, [open, step]);
  useLayoutEffect(() => { measure(); }, [measure]);
  useEffect(() => { if (!open) return; addEventListener("resize", measure); return () => removeEventListener("resize", measure); }, [open, measure]);
  useEffect(() => { if (open) nextRef.current?.focus(); }, [open, i]);

  const finish = useCallback(() => { setOpen(false); updateSettings({ onboarded: TOUR_VERSION }); }, []);
  const go = useCallback((d) => setI((x) => { const n = x + d; if (n >= STEPS.length) { finish(); return x; } return Math.max(0, n); }), [finish]);
  useEffect(() => {
    if (!open) return;
    const k = (e) => {
      if (e.key === "Escape") { e.preventDefault(); finish(); }
      else if (e.key === "ArrowRight") { e.preventDefault(); go(1); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); go(-1); }
    };
    addEventListener("keydown", k);
    return () => removeEventListener("keydown", k);
  }, [open, go, finish]);

  if (!open) return null;
  const pad = 6;
  const cardW = Math.min(340, innerWidth - 24);
  let cardStyle;
  if (rect) {
    const below = rect.y + rect.h + 12 + 200 < innerHeight;
    const left = Math.max(12, Math.min(rect.x + rect.w / 2 - cardW / 2, innerWidth - cardW - 12));
    cardStyle = { width: cardW, left, top: below ? rect.y + rect.h + pad + 10 : undefined, bottom: below ? undefined : Math.max(12, innerHeight - rect.y + pad + 10) };
  } else cardStyle = { width: cardW, left: (innerWidth - cardW) / 2, top: Math.max(24, innerHeight / 2 - 130) };
  const last = i === STEPS.length - 1;

  return createPortal(
    <div className="ux-tour" role="presentation">
      <div className="ux-tour-shade" aria-hidden="true" style={rect ? { left: rect.x - pad, top: rect.y - pad, width: rect.w + pad * 2, height: rect.h + pad * 2 } : { left: "50%", top: "50%", width: 0, height: 0 }} />
      <div role="dialog" aria-modal="true" aria-labelledby="ux-tour-t" aria-describedby="ux-tour-b" className="ux-tour-card" style={cardStyle}>
        <div className="flex items-start gap-2">
          <h2 id="ux-tour-t" className="m-0 text-[14px] font-semibold flex-1">{step.t}</h2>
          <button type="button" className="ux-x" onClick={finish} aria-label="Bỏ qua hướng dẫn"><X size={14} aria-hidden="true" /></button>
        </div>
        <p id="ux-tour-b" className="m-0 mt-2 text-[12.5px] text-muted leading-relaxed">{step.b}</p>
        <div className="flex items-center gap-2 mt-3">
          <span className="text-[11.5px] text-faint" aria-live="polite">Bước {i + 1}/{STEPS.length}</span>
          <div className="ml-auto flex gap-2">
            {i > 0 && <button type="button" className="btn" onClick={() => go(-1)}><ChevronLeft size={14} aria-hidden="true" /> Lùi</button>}
            <button ref={nextRef} type="button" className="btn ux-btn-primary" onClick={() => go(1)}>{last ? "Bắt đầu dùng" : "Tiếp"} {!last && <ChevronRight size={14} aria-hidden="true" />}</button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
