// Phím tắt toàn cục kiểu GitHub: `g` rồi chữ để chuyển trang; / tìm; ? trợ giúp; t đổi giao diện; [ thu/mở thanh nav.
import { useEffect, useRef, useState } from "react";
import { Dialog } from "./dialog";

export const GO_KEYS = [
  ["t", "terminal", "Terminal"], ["o", "tong-quan", "Tổng quan"], ["m", "thi-truong", "Thị trường"], ["p", "phan-tich", "Phân tích"], ["n", "tin-tuc", "Tin tức"],
  ["l", "lich", "Lịch kinh tế"], ["e", "chuyen-gia", "Chuyên gia"], ["a", "tai-khoan", "Tài khoản"], ["c", "canh-bao", "Cảnh báo"],
  ["w", "danh-sach", "Danh sách theo dõi"], ["j", "nhat-ky", "Nhật ký giao dịch"], ["s", "he-thong", "Hệ thống"],
  ["b", "ban-tin", "Bản tin"], ["r", "bao-cao", "Báo cáo"], ["v", "chung-khoan-vn", "Chứng khoán VN"], ["u", "khach-hang", "Khách hàng"],
  ["f", "doi-tai-khoan", "Đội tài khoản (master)"], ["x", "su-co", "Sự cố (master)"], ["k", "cai-dat", "Cài đặt"], ["h", "tro-giup", "Trợ giúp & thuật ngữ"], ["i", "gioi-thieu", "Giới thiệu"], ["d", "design", "Design system (nội bộ)"],
];

const typing = (t) => !!t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));

export function useShortcuts({ onPalette, onHelp, onTheme, onRail }) {
  const [armed, setArmed] = useState(false);
  const timer = useRef(null);
  const fn = useRef({});
  fn.current = { onPalette, onHelp, onTheme, onRail };
  useEffect(() => {
    let g = false;
    const disarm = () => { g = false; setArmed(false); clearTimeout(timer.current); };
    const onKey = (e) => {
      if (e.isComposing) return;
      if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "k") { e.preventDefault(); disarm(); fn.current.onPalette(); return; }
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (typing(e.target) || document.querySelector('[aria-modal="true"]')) { if (g) disarm(); return; }
      if (g) {
        const hit = GO_KEYS.find(([k]) => k === e.key.toLowerCase());
        disarm();
        if (hit) { e.preventDefault(); location.hash = `#/${hit[1]}`; }
        return;
      }
      if (e.key === "g") { g = true; setArmed(true); timer.current = setTimeout(disarm, 1500); return; }
      if (e.key === "/") { e.preventDefault(); fn.current.onPalette(); }
      else if (e.key === "?") { e.preventDefault(); fn.current.onHelp(); }
      else if (e.key === "t") fn.current.onTheme();
      else if (e.key === "[") fn.current.onRail();
      else if (e.key === "i" && document.querySelector('nav a[href="#/su-co"]')) { e.preventDefault(); location.hash = "#/su-co"; } // hộp sự cố (chỉ khi vai trò có trang này)
    };
    addEventListener("keydown", onKey);
    return () => { removeEventListener("keydown", onKey); clearTimeout(timer.current); };
  }, []);
  return armed;
}

export function GPending() {
  return (
    <div role="status" aria-live="polite" className="fixed bottom-[calc(var(--nav-h)+8px)] lg:bottom-4 right-4 z-[70] rounded-md border border-line2 bg-panel px-3 py-2 text-[12.5px] shadow-xl">
      <kbd>g</kbd> … nhấn phím tiếp theo (t, o, m, p, n, l, e, a, c, w, s)
    </div>
  );
}

const Row = ({ keys, label }) => (
  <li className="flex items-center justify-between gap-3 py-[5px]">
    <span>{label}</span>
    <span className="flex gap-1 shrink-0">{keys.map((k, i) => <kbd key={i} className="num text-[11px] border border-line2 bg-panel2 rounded px-[6px] py-[1px]">{k}</kbd>)}</span>
  </li>
);

export function ShortcutsHelp({ open, onClose }) {
  return (
    <Dialog open={open} onClose={onClose} title="Phím tắt" description="Không hoạt động khi bạn đang gõ trong ô nhập liệu.">
      <div className="p-3 grid gap-4 sm:grid-cols-2">
        <section aria-label="Chung">
          <h3 className="m-0 mb-1 text-[12px] text-muted">Chung</h3>
          <ul className="m-0 p-0 list-none text-[13px]">
            <Row keys={["Ctrl", "K"]} label="Mở tìm nhanh (⌘K trên Mac)" />
            <Row keys={["/"]} label="Mở tìm nhanh" />
            <Row keys={["?"]} label="Bảng phím tắt này" />
            <Row keys={["t"]} label="Đổi giao diện sáng/tối" />
            <Row keys={["["]} label="Thu/mở thanh điều hướng" />
            <Row keys={["Esc"]} label="Đóng hộp thoại" />
          </ul>
        </section>
        <section aria-label="Chuyển trang">
          <h3 className="m-0 mb-1 text-[12px] text-muted">Chuyển trang (nhấn g rồi chữ)</h3>
          <ul className="m-0 p-0 list-none text-[13px]">{GO_KEYS.map(([k, , l]) => <Row key={k} keys={["g", k]} label={l} />)}</ul>
        </section>
      </div>
    </Dialog>
  );
}
