import { useState } from "react";
import { BellRing, Eye, LayoutGrid, Plug, ShieldAlert } from "lucide-react";
import { Sheet } from "./ui";
import { usePrefs } from "../lib/prefs";
import { askPermission, pushSupported } from "../lib/notifstore";
import { t } from "../lib/i18n";

const makeSteps = () => [
  { icon: Eye, title: t("Chào mừng bạn"), body: (
    <>
      <p className="m-0">{t("Đây là ứng dụng theo dõi tài khoản MT4/MT5 của bạn: vốn, vị thế, rủi ro, nhật ký giao dịch và thị trường.")}</p>
      <p className="m-0 mt-2"><b>{t("Ứng dụng chỉ xem và phân tích, không đặt, sửa hay đóng lệnh.")}</b> {t("Bạn không bao giờ cần đưa mật khẩu giao dịch MT cho ứng dụng.")}</p>
    </>) },
  { icon: Plug, title: t("Dữ liệu đến từ EA"), body: (
    <>
      <p className="m-0">{t("EA là chương trình nhỏ gắn trong MT4/MT5, chỉ đọc và gửi số liệu tài khoản về đây. Chấm màu cạnh số tài khoản cho biết EA còn kết nối:")}</p>
      <ul className="m-0 mt-2 pl-4 grid gap-1"><li><span className="live-dot on" /> {t("xanh: dữ liệu mới trong vài chục giây")}</li><li><span className="live-dot warn" /> {t("vàng: chậm")}</li><li><span className="live-dot off" /> {t("đỏ: mất kết nối, số liệu có thể đã cũ")}</li></ul>
      <p className="m-0 mt-2">{t("Hướng dẫn gắn EA có trong mục")} <b>{t("Trợ giúp")}</b>.</p>
    </>) },
  { icon: LayoutGrid, title: t("Các khối chính"), body: (
    <ul className="m-0 pl-4 grid gap-1.5">
      <li><b>{t("Tổng quan:")}</b> {t("vốn, lãi/lỗ hôm nay, đường vốn và sức khoẻ margin.")}</li>
      <li><b>{t("Vị thế:")}</b> {t("lệnh đang mở, lệnh chờ, tiếp xúc theo mã và tiền tệ.")}</li>
      <li><b>{t("Rủi ro:")}</b> {t("còn cách ngưỡng bị đóng lệnh bao xa, kịch bản biến động mạnh.")}</li>
      <li><b>{t("Nhật ký:")}</b> {t("thống kê hiệu suất, lịch lãi/lỗ, ghi chú và nhãn cho từng lệnh.")}</li>
      <li><b>{t("Thị trường:")}</b> {t("biểu đồ, chỉ báo, tin và lịch kinh tế.")}</li>
    </ul>) },
  { icon: ShieldAlert, title: t("Cảnh báo & thông báo"), body: null },
];

export default function Onboarding() {
  const { prefs, set } = usePrefs();
  const [i, setI] = useState(0);
  const [perm, setPerm] = useState(typeof Notification === "undefined" ? "unsupported" : Notification.permission);
  if (prefs.onboarded) return null;
  const STEPS = makeSteps();
  const s = STEPS[i], last = i === STEPS.length - 1;
  const done = () => set({ onboarded: true });
  return (
    <Sheet title={s.title} onClose={done}>
      <div className="grid gap-3 text-[14px]">
        <div className="flex items-center gap-1.5" aria-label={t("Bước {i} trên {n}", { i: i + 1, n: STEPS.length })}>{STEPS.map((_, k) => <span key={k} className="h-1.5 flex-1 rounded-full" style={{ background: k <= i ? "var(--accent)" : "var(--line2)" }} />)}</div>
        <s.icon size={30} className="text-accent" aria-hidden="true" />
        {s.body || (
          <>
            <p className="m-0">{t("Tạo cảnh báo khi giá chạm ngưỡng, margin thấp hoặc EA mất kết nối ở mục")} <a className="underline" href="#/canh-bao" onClick={done}>{t("Cảnh báo")}</a>. {t("Thông báo hiện trong chuông ở đầu trang.")}</p>
            {pushSupported() && perm === "default" && <button className="btn" onClick={async () => setPerm(await askPermission())}><BellRing size={16} aria-hidden="true" /> {t("Bật thông báo trên thiết bị")}</button>}
            {perm === "granted" && <p className="m-0 text-up">{t("Đã bật thông báo trên thiết bị.")}</p>}
            <p className="m-0 text-muted text-[13px]">{t("Mẹo: thêm ứng dụng vào màn hình chính để mở nhanh như một app (xem mục Cài đặt).")}</p>
          </>
        )}
        <div className="flex gap-2 pt-1">
          {i > 0 && <button className="btn" onClick={() => setI(i - 1)}>{t("Quay lại")}</button>}
          <button className="btn primary ml-auto" onClick={last ? done : () => setI(i + 1)}>{last ? t("Bắt đầu") : t("Tiếp")}</button>
          {!last && <button className="btn ghost" onClick={done}>{t("Bỏ qua")}</button>}
        </div>
      </div>
    </Sheet>
  );
}
