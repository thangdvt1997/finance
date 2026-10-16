// Giới thiệu: mục đích, phiên bản, ghi công mã nguồn mở (chỉ thư viện/công cụ), thông tin hỗ trợ để sao chép.
import { useMemo, useState } from "react";
import { ExternalLink, Heart, Info, LifeBuoy, ShieldCheck } from "lucide-react";
import { Disclaimer, PageHead, Panel } from "../components/ui";
import { BUILD_TIME, VERSION } from "../ux/changelog";
import { CREDITS, INSPIRATION } from "../ux/credits";
import { copyText } from "../ux/actions";
import { useSettings, effectiveTheme } from "../ux/settings";
import { tzOffsetLabel, fmtCfg } from "../ux/fmtconfig";
import { useStream } from "../lib/stream";
import { usePrefsState } from "../lib/prefs";
import { toast } from "../ux/bus";


export const meta = { path: "gioi-thieu", label: "Giới thiệu", group: "Tiện ích", icon: Info, order: 30, roles: ["master", "client"], keywords: "ghi cong open source giay phep phien ban about credits" };
export default function About() {
  const [s] = useSettings();
  const st = useStream();
  const prefs = usePrefsState();
  const [copied, setCopied] = useState(false);
  const info = useMemo(() => [
    ["Phiên bản giao diện", VERSION],
    ["Dựng lúc", BUILD_TIME || "—"],
    ["Giao diện", `${effectiveTheme(s)} (${s.theme}) · nhấn ${s.accent} · mật độ ${s.density} · chữ ${s.fontScale}%`],
    ["Múi giờ hiển thị", `${fmtCfg.tz} (${tzOffsetLabel()})`],
    ["Màn hình", `${innerWidth}×${innerHeight} @${devicePixelRatio}x`],
    ["Kênh thời gian thực", st.status],
    ["Tuỳ chọn máy chủ", prefs.available ? `sẵn sàng (rev ${prefs.rev})` : "không khả dụng"],
    ["Trình duyệt", navigator.userAgent],
  ], [s, st.status, prefs.available, prefs.rev]); // eslint-disable-line react-hooks/exhaustive-deps
  const text = info.map(([k, v]) => `${k}: ${v}`).join("\n");
  return (
    <>
      <PageHead title="Giới thiệu" sub="Trạm theo dõi thị trường: giá, tin, lịch kinh tế và tài khoản MT4/MT5 ở chế độ chỉ-đọc, tiếng Việt, giờ Việt Nam." />
      <div className="grid gap-3 lg:grid-cols-2 items-start">
        <Panel title="Về hệ thống" icon={Info}>
          <div className="ux-prose text-[13px]">
            <p>Giao diện này là cửa sổ <b>chỉ-đọc</b> vào hệ thống theo dõi thị trường: không có đường đặt, sửa hay đóng lệnh. Thông tin chỉ để tham khảo, <b>không phải khuyến nghị đầu tư</b>.</p>
            <p>Phiên bản <b className="num">{VERSION}</b>{BUILD_TIME ? <>, dựng <span className="num">{BUILD_TIME.slice(0, 16).replace("T", " ")} UTC</span></> : null}. Mọi tài nguyên được đóng gói sẵn; giao diện không tải mã hay phông chữ từ bên ngoài.</p>
            <p><a href="#/tro-giup?tab=phien-ban">Ghi chú phiên bản</a> · <a href="#/tro-giup">Trợ giúp</a> · <a href="#/design">Design system nội bộ</a></p>
          </div>
          <Disclaimer>Giao dịch có rủi ro mất vốn. Hiệu suất quá khứ và kết quả mô phỏng không bảo đảm kết quả tương lai.</Disclaimer>
        </Panel>
        <Panel title="Thông tin hỗ trợ" icon={LifeBuoy} right={<button type="button" className="btn" onClick={async () => { const ok = await copyText(text); setCopied(ok); toast({ tone: ok ? "ok" : "error", title: ok ? "Đã sao chép thông tin hỗ trợ" : "Không sao chép được", ttl: 2500 }); }}>{copied ? "Đã sao chép" : "Sao chép"}</button>}>
          <dl className="m-0 grid gap-1 text-[12.5px]" style={{ gridTemplateColumns: "max-content 1fr", columnGap: "1rem" }}>
            {info.map(([k, v]) => <div key={k} className="contents"><dt className="text-muted">{k}</dt><dd className="m-0 num break-words min-w-0">{v}</dd></div>)}
          </dl>
          <p className="m-0 mt-2 text-[12px] text-faint">Không chứa mật khẩu hay dữ liệu tài khoản. Gửi kèm khi báo lỗi cho quản trị viên.</p>
        </Panel>
        <Panel title="Ghi công mã nguồn mở" icon={Heart} className="lg:col-span-2">
          <p className="m-0 mb-3 text-[12.5px] text-muted max-w-[80ch]">Giao diện được xây từ các dự án mã nguồn mở giấy phép cho phép thương mại (MIT, Apache-2.0, ISC, BSD, OFL). Cảm ơn các tác giả. Logo TradingView trên biểu đồ được giữ nguyên theo yêu cầu ghi công của giấy phép Apache-2.0.</p>
          <div className="scroll-x">
            <table className="tbl" aria-label="Thành phần mã nguồn mở">
              <thead><tr><th>Thành phần</th><th>Dùng để</th><th>Giấy phép</th><th><span className="sr-only">Liên kết</span></th></tr></thead>
              <tbody>
                {CREDITS.map((c) => (
                  <tr key={c.name}><td className="font-semibold">{c.name}</td><td className="text-muted">{c.use}</td><td>{c.lic}</td>
                    <td><a href={c.url} target="_blank" rel="noopener noreferrer" aria-label={`Mã nguồn của ${c.name} (mở tab mới)`} className="inline-flex items-center gap-1"><ExternalLink size={12} aria-hidden="true" /> Mã nguồn</a></td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3 className="m-0 mt-4 mb-1 text-[12.5px] text-muted flex items-center gap-1"><ShieldCheck size={13} aria-hidden="true" /> Nguồn tham khảo thiết kế (không sao chép mã)</h3>
          <ul className="m-0 pl-5 text-[12.5px] grid gap-1">{INSPIRATION.map((i) => <li key={i.name}><b>{i.name}</b> ({i.lic}) — {i.note}</li>)}</ul>
          <p className="m-0 mt-2 text-[12px] text-faint">Các dự án giấy phép copyleft (GPL/AGPL) chỉ được xem ý tưởng bố cục, không dùng mã. Danh sách đầy đủ và phiên bản cố định nằm trong THIRD_PARTY.md của dự án.</p>
        </Panel>
      </div>
    </>
  );
}
