// Bảng phím tắt (nhấn ?). Có ô lọc; trang khác đăng ký thêm mục bằng registerShortcuts(tiêu đề, [[phím[], mô tả]]).
import { useMemo, useState } from "react";
import { Dialog } from "../dialog";
import { GO_KEYS } from "../shortcuts";
import { foldText } from "../../ux/glossary";

const extra = new Map();
/** Đăng ký nhóm phím tắt hiển thị trong bảng. Trả hàm huỷ. */
export function registerShortcuts(title, rows) { extra.set(title, rows); return () => extra.delete(title); }

const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || "");
const MOD = isMac ? "⌘" : "Ctrl";

const GENERAL = [
  [[MOD, "K"], "Mở tìm nhanh và lệnh"],
  [["/"], "Mở tìm nhanh"],
  [["?"], "Bảng phím tắt này"],
  [["t"], "Đổi giao diện sáng/tối"],
  [["["], "Thu/mở thanh điều hướng"],
  [["Alt", "N"], "Mở trung tâm thông báo"],
  [["Esc"], "Đóng hộp thoại / menu"],
  [["Tab"], "Đi tới phần tử kế (có liên kết “Bỏ qua điều hướng” ở đầu trang)"],
];
const PALETTE = [
  [[">"], "Chỉ tìm lệnh (đổi giao diện, xuất bảng, đặt lại...)"],
  [["$"], "Chỉ tìm mã: mở biểu đồ, thêm danh sách, tạo cảnh báo"],
  [["#"], "Tìm trong tin mới"],
  [["?"], "Tra thuật ngữ và câu hỏi thường gặp"],
  [["cảnh báo eurusd 1.0850"], "Mở biểu mẫu cảnh báo đã điền sẵn mã và giá"],
  [["eurusd h4"], "Mở biểu đồ đúng mã và khung H4"],
];
const TABLE = [
  [["↑", "↓"], "Trong bảng: nhảy giữa các dòng, giữ nguyên cột (khi đang ở nút/liên kết trong ô)"],
  [["Home", "End"], "Trong bảng: về ô đầu/cuối dòng"],
  [["Enter"], "Mở mục đang chọn"],
];
const CHART = [
  [[","], "Khung thời gian nhỏ hơn"], [["."], "Khung thời gian lớn hơn"], [["i"], "Mở bảng chỉ báo"], [["s"], "Bật/tắt tín hiệu"],
  [["p"], "Bật/tắt bảng bên"], [["l"], "Thang log"], [["n"], "Nam châm (hít giá)"], [["z"], "Vừa khung xem"],
  [["Shift", "→"], "Về nến mới nhất"], [[MOD, "Z"], "Hoàn tác nét vẽ"], [["Del"], "Xoá nét vẽ đang chọn"], [["Esc"], "Huỷ công cụ / thoát toàn màn hình"],
];

const Row = ({ keys, label }) => (
  <li className="flex items-center justify-between gap-3 py-[5px]">
    <span className="min-w-0">{label}</span>
    <span className="flex gap-1 shrink-0 flex-wrap justify-end">{keys.map((k, i) => <kbd key={i} className="ux-kbd num">{k}</kbd>)}</span>
  </li>
);

export function Cheatsheet({ open, onClose }) {
  const [f, setF] = useState("");
  const sections = useMemo(() => {
    const s = [
      ["Chung", GENERAL],
      ["Chuyển trang (nhấn g rồi chữ)", GO_KEYS.map(([k, , l]) => [["g", k], l])],
      ["Tìm nhanh (Ctrl K): cú pháp", PALETTE],
      ["Bảng", TABLE],
      ["Biểu đồ (trang Thị trường)", CHART],
      ...[...extra.entries()],
    ];
    const t = foldText(f.trim());
    if (!t) return s;
    return s.map(([title, rows]) => [title, rows.filter(([k, l]) => foldText(`${l} ${k.join(" ")} ${title}`).includes(t))]).filter(([, r]) => r.length);
  }, [f, open]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Dialog open={open} onClose={onClose} title="Phím tắt" description="Phím đơn không hoạt động khi bạn đang gõ trong ô nhập liệu.">
      <div className="px-3 pt-2">
        <label className="sr-only" htmlFor="ux-keys-f">Lọc phím tắt</label>
        <input id="ux-keys-f" className="field w-full" type="search" placeholder="Lọc: ví dụ “cảnh báo”, “khung”" value={f} onChange={(e) => setF(e.target.value)} autoComplete="off" />
      </div>
      <div className="p-3 grid gap-4 sm:grid-cols-2">
        {sections.length === 0 && <p className="m-0 text-muted">Không có phím tắt khớp “{f}”.</p>}
        {sections.map(([title, rows]) => (
          <section key={title} aria-label={title}>
            <h3 className="m-0 mb-1 text-[12px] text-muted">{title}</h3>
            <ul className="m-0 p-0 list-none text-[13px]">{rows.map(([k, l], i) => <Row key={i} keys={k} label={l} />)}</ul>
          </section>
        ))}
      </div>
    </Dialog>
  );
}
